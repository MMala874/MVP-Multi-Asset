from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import importlib.util
import sys
from typing import Any, Dict, Iterable, List

import numpy as np
import pandas as pd

from backtest.trade_log import TRADE_LOG_COLUMNS
from configs.models import Config
from features.indicators import adx, atr, ema
from features.regime import compute_atr_pct, rolling_percentile
from risk.allocator import RiskAllocator
from risk.conflict import resolve_conflicts

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types" / "__init__.py"
_spec = importlib.util.spec_from_file_location("project_types", _TYPES_PATH)
_types_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("project_types", _types_module)
assert _spec and _spec.loader
_spec.loader.exec_module(_types_module)

Side = _types_module.Side
OrderIntent = _types_module.OrderIntent
SystemState = _types_module.SystemState

STRATEGY_MAP = {
    "S1_TREND_EMA_ATR_ADX": "strategies.s1_trend_ema_atr_adx",
    "S2_MR_ZSCORE_EMA_REGIME": "strategies.s2_mr_zscore_ema_regime",
    "S3_BREAKOUT_ATR_REGIME_EMA200": "strategies.s3_breakout_atr_regime_ema200",
}


@dataclass
class _StrategySpec:
    name: str
    module: Any
    params: Dict[str, Any]


class LiveOrchestrator:
    def __init__(self, config: Config) -> None:
        _validate_bar_contract(config)
        self._config = config
        self._strategies = _load_strategies(config)
        self._allocator = RiskAllocator(config)
        self._trade_id = 1
        self._trade_log: List[Dict[str, Any]] = []
        self._state: SystemState = SystemState.RUNNING

    def update_state(self, state: SystemState) -> None:
        self._state = state

    def step(self, new_bar_data: Dict[str, pd.DataFrame]) -> List[OrderIntent]:
        if self._state == SystemState.SAFE_MODE:
            self._manage_positions_stub(new_bar_data)
            return []

        prepared = _prepare_features(new_bar_data, self._strategies, self._config)
        orders: List[OrderIntent] = []

        for symbol, df in prepared.items():
            if df.empty:
                continue
            idx = len(df) - 1
            signal_time = _resolve_time(df, idx)
            context = {
                "df": df,
                "idx": idx,
                "symbol": symbol,
                "current_time": signal_time,
            }

            signals = []
            for spec in self._strategies:
                ctx = dict(context)
                ctx["config"] = spec.params
                signal = spec.module.generate_signal(ctx)
                if signal.side == Side.FLAT:
                    continue
                signals.append(signal)

            if not signals:
                continue

            filtered = resolve_conflicts(
                signals,
                policy=self._config.risk.conflict_policy,
                priority_order=self._config.risk.priority_order,
            )

            state = {"prices": {symbol: float(df["close"].iat[idx])}}
            orders_for_symbol = self._allocator.allocate(filtered, state)
            orders.extend(orders_for_symbol)

            for order in orders_for_symbol:
                self._trade_log.append(
                    _build_trade_log_entry(
                        trade_id=self._trade_id,
                        order=order,
                        symbol=symbol,
                        signal_time=signal_time,
                        signal_idx=idx,
                        regime_snapshot=df.get("regime_snapshot", pd.Series([None])).iat[idx],
                    )
                )
                self._trade_id += 1

        self._execution_stub(orders)
        return orders

    def trade_log(self) -> pd.DataFrame:
        return pd.DataFrame(self._trade_log, columns=TRADE_LOG_COLUMNS)

    @staticmethod
    def _execution_stub(orders: List[OrderIntent]) -> None:
        _ = orders
        return None

    @staticmethod
    def _manage_positions_stub(new_bar_data: Dict[str, pd.DataFrame]) -> None:
        _ = new_bar_data
        return None


def _validate_bar_contract(config: Config) -> None:
    if config.bar_contract.signal_on != "close":
        raise ValueError("bar_contract.signal_on must be close")
    if config.bar_contract.fill_on != "open_next":
        raise ValueError("bar_contract.fill_on must be open_next")
    if config.bar_contract.allow_bar0:
        raise ValueError("bar_contract.allow_bar0 must be false")


def _load_strategies(config: Config) -> List[_StrategySpec]:
    specs: List[_StrategySpec] = []
    for name in config.strategies.enabled:
        module_path = STRATEGY_MAP.get(name)
        if module_path is None:
            raise ValueError(f"Unsupported strategy: {name}")
        module = __import__(module_path, fromlist=["generate_signal"])
        params = dict(config.strategies.params.get(name, {}))
        specs.append(_StrategySpec(name=name, module=module, params=params))
    return specs


def _prepare_features(
    df_by_symbol: Dict[str, pd.DataFrame],
    strategies: Iterable[_StrategySpec],
    config: Config,
) -> Dict[str, pd.DataFrame]:
    prepared: Dict[str, pd.DataFrame] = {}
    for symbol, df in df_by_symbol.items():
        df_local = df.copy()
        df_local = _ensure_ohlc(df_local)

        for spec in strategies:
            df_local = _apply_strategy_features(df_local, spec)

        if "atr" not in df_local:
            df_local["atr"] = atr(df_local, 14)

        df_local["regime_snapshot"] = _compute_regime(
            df_local,
            window=config.regime.atr_pct_window,
            atr_n=config.regime.atr_pct_n,
        )
        prepared[symbol] = df_local
    return prepared


def _ensure_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required OHLC columns: {sorted(missing)}")
    return df


def _apply_strategy_features(df: pd.DataFrame, spec: _StrategySpec) -> pd.DataFrame:
    if spec.name == "S1_TREND_EMA_ATR_ADX":
        ema_fast = int(spec.params.get("ema_fast", 20))
        ema_slow = int(spec.params.get("ema_slow", 50))
        atr_period = int(spec.params.get("atr_period", 14))
        adx_period = int(spec.params.get("adx_period", 14))
        if "ema_fast" not in df:
            df["ema_fast"] = ema(df["close"], ema_fast)
        if "ema_slow" not in df:
            df["ema_slow"] = ema(df["close"], ema_slow)
        if "atr" not in df:
            df["atr"] = atr(df, atr_period)
        if "adx" not in df:
            df["adx"] = adx(df, adx_period)
    elif spec.name == "S2_MR_ZSCORE_EMA_REGIME":
        ema_base = int(spec.params.get("ema_regime", spec.params.get("ema_base", 200)))
        adx_period = int(spec.params.get("adx_period", 14))
        if "ema_base" not in df:
            df["ema_base"] = ema(df["close"], ema_base)
        if "adx" not in df:
            df["adx"] = adx(df, adx_period)
    elif spec.name == "S3_BREAKOUT_ATR_REGIME_EMA200":
        atr_period = int(spec.params.get("atr_period", 14))
        ema_period = int(spec.params.get("ema200", 200))
        if "atr" not in df:
            df["atr"] = atr(df, atr_period)
        if "ema200" not in df:
            df["ema200"] = ema(df["close"], ema_period)
    return df


def _compute_regime(df: pd.DataFrame, window: int, atr_n: int) -> pd.Series:
    if "atr" not in df:
        return pd.Series(["UNKNOWN"] * len(df), index=df.index)
    atr_pct = compute_atr_pct(df, atr_n=atr_n)
    p35_series = rolling_percentile(atr_pct, window=window, q=35)
    p75_series = rolling_percentile(atr_pct, window=window, q=75)
    regime = pd.Series(["UNKNOWN"] * len(df), index=df.index)
    valid_mask = atr_pct.notna() & p35_series.notna() & p75_series.notna()
    if valid_mask.any():
        atr_vals = atr_pct[valid_mask]
        p35_vals = p35_series[valid_mask]
        p75_vals = p75_series[valid_mask]
        regime.loc[valid_mask] = np.where(
            atr_vals < p35_vals,
            "LOW",
            np.where(atr_vals < p75_vals, "MID", "HIGH"),
        )
    return regime


def _resolve_time(df: pd.DataFrame, idx: int) -> datetime:
    if isinstance(df.index, pd.DatetimeIndex):
        return df.index[idx].to_pydatetime()
    if "timestamp" in df.columns:
        return pd.to_datetime(df["timestamp"].iat[idx]).to_pydatetime()
    return datetime.utcfromtimestamp(idx)


def _build_trade_log_entry(
    trade_id: int,
    order: OrderIntent,
    symbol: str,
    signal_time: datetime,
    signal_idx: int,
    regime_snapshot: Any,
) -> Dict[str, Any]:
    return {
        "trade_id": trade_id,
        "order_id": f"live-{symbol}-{signal_idx}-{trade_id}",
        "symbol": symbol,
        "strategy_id": order.strategy_id,
        "side": order.side.value,
        "qty": order.qty,
        "signal_time": signal_time,
        "signal_idx": signal_idx,
        "fill_time": None,
        "entry_price": None,
        "exit_time": None,
        "exit_price": None,
        "pnl": None,
        "pnl_pct": None,
        "spread_used": None,
        "slippage_used": None,
        "scenario": "LIVE",
        "regime_snapshot": regime_snapshot,
        "reason_codes": ";".join([f"{k}={v}" for k, v in order.meta.items()]),
    }


__all__ = ["LiveOrchestrator"]
