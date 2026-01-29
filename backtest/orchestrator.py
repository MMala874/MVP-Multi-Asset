from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

from configs.models import Config
from execution.cost_model import CostModel
from execution.fill_rules import get_fill_price
from features.indicators import adx, atr, ema
from features.regime import classify_vol_regime, compute_atr_pct
from risk.allocator import RiskAllocator
from risk.conflict import resolve_conflicts
import importlib.util
from pathlib import Path
import sys

from backtest.metrics import compute_metrics
from backtest.report import build_report
from backtest.trade_log import TRADE_LOG_COLUMNS

_TYPES_PATH = Path(__file__).resolve().parents[1] / "types" / "__init__.py"
_spec = importlib.util.spec_from_file_location("project_types", _TYPES_PATH)
_types_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("project_types", _types_module)
assert _spec and _spec.loader
_spec.loader.exec_module(_types_module)

Scenario = _types_module.Scenario
Side = _types_module.Side

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


class BacktestOrchestrator:
    def run(self, df_by_symbol: Dict[str, pd.DataFrame], config: Config) -> Tuple[pd.DataFrame, Dict[str, object]]:
        _validate_bar_contract(config)
        strategies = _load_strategies(config)
        prepared = _prepare_features(df_by_symbol, strategies)

        scenario_trades: List[pd.DataFrame] = []
        for scenario in Scenario:
            trades = _run_scenario(prepared, config, strategies, scenario.value)
            scenario_trades.append(trades)

        trades_df = pd.concat(scenario_trades, ignore_index=True) if scenario_trades else _empty_trades()
        metrics = compute_metrics(trades_df)
        report = build_report(trades_df, metrics)
        return trades_df, report


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
) -> Dict[str, pd.DataFrame]:
    prepared: Dict[str, pd.DataFrame] = {}
    for symbol, df in df_by_symbol.items():
        df_local = df.copy()
        df_local = _ensure_ohlc(df_local)

        for spec in strategies:
            df_local = _apply_strategy_features(df_local, spec)

        if "atr" not in df_local:
            df_local["atr"] = atr(df_local, 14)

        df_local["regime_snapshot"] = _compute_regime(df_local)
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


def _compute_regime(df: pd.DataFrame) -> pd.Series:
    if "atr" not in df:
        return pd.Series(["UNKNOWN"] * len(df), index=df.index)
    atr_pct = compute_atr_pct(df, atr_n=1)
    valid = atr_pct.dropna()
    if valid.empty:
        return pd.Series(["UNKNOWN"] * len(df), index=df.index)
    p35 = float(valid.quantile(0.35))
    p75 = float(valid.quantile(0.75))
    return classify_vol_regime(atr_pct, p35, p75)


def _run_scenario(
    df_by_symbol: Dict[str, pd.DataFrame],
    config: Config,
    strategies: Iterable[_StrategySpec],
    scenario: str,
) -> pd.DataFrame:
    allocator = RiskAllocator(config)
    cost_model = CostModel(config)

    trades: List[Dict[str, Any]] = []
    trade_id = 1

    for symbol, df in df_by_symbol.items():
        for idx in range(len(df) - 1):
            signal_time = _resolve_time(df, idx)
            signals = []
            for spec in strategies:
                df_hist = df.iloc[: idx + 1].copy()
                idx_hist = len(df_hist) - 1
                ctx = {
                    "df": df_hist,
                    "idx": idx_hist,
                    "symbol": symbol,
                    "current_time": signal_time,
                }
                ctx["config"] = spec.params
                signal = spec.module.generate_signal(ctx)
                if signal.side == Side.FLAT:
                    continue
                signals.append(signal)

            if not signals:
                continue

            filtered = resolve_conflicts(
                signals,
                policy=config.risk.conflict_policy,
                priority_order=config.risk.priority_order,
            )

            state = {"prices": {symbol: float(df["close"].iat[idx])}}
            orders = allocator.allocate(filtered, state)

            for order in orders:
                entry_price = get_fill_price(df, idx_t=idx, side=order.side.value)
                spread_used = cost_model.spread_pips(symbol, scenario)
                slippage_used = cost_model.slippage_pips(df, idx, symbol, df["atr"], scenario)
                entry_cost, exit_cost = cost_model.trade_cost_pips(
                    symbol=symbol,
                    idx_t=idx,
                    scenario=scenario,
                    df=df,
                    atr_series=df["atr"],
                )
                entry_price_adj = _apply_cost(entry_price, entry_cost, order.side)
                exit_time = _resolve_time(df, idx + 1)
                exit_price_raw = float(df["close"].iat[idx + 1])
                exit_price_adj = _apply_cost(exit_price_raw, exit_cost, _opposite_side(order.side))

                pnl = _calc_pnl(order.side, order.qty, entry_price_adj, exit_price_adj)
                pnl_pct = pnl / (abs(entry_price_adj) * abs(order.qty)) if order.qty != 0 else 0.0

                reason_codes = _encode_reason_codes(order.meta, filtered)

                trades.append(
                    {
                        "trade_id": trade_id,
                        "order_id": f"{scenario}-{symbol}-{idx}-{trade_id}",
                        "symbol": symbol,
                        "strategy_id": order.strategy_id,
                        "side": order.side.value,
                        "qty": order.qty,
                        "signal_time": signal_time,
                        "signal_idx": idx,
                        "fill_time": _resolve_time(df, idx + 1),
                        "entry_price": entry_price_adj,
                        "exit_time": exit_time,
                        "exit_price": exit_price_adj,
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "spread_used": spread_used,
                        "slippage_used": slippage_used,
                        "scenario": scenario,
                        "regime_snapshot": df["regime_snapshot"].iat[idx],
                        "reason_codes": reason_codes,
                    }
                )
                trade_id += 1

    trades_df = pd.DataFrame(trades, columns=TRADE_LOG_COLUMNS)
    return trades_df


def _encode_reason_codes(meta: Dict[str, str], signals: Iterable[Any]) -> str:
    codes = []
    for signal in signals:
        for key, value in signal.tags.items():
            codes.append(f"{key}={value}")
    for key, value in meta.items():
        codes.append(f"{key}={value}")
    return ";".join(codes)


def _apply_cost(price: float, cost: float, side: Side) -> float:
    if side == Side.LONG:
        return price + cost
    if side == Side.SHORT:
        return price - cost
    return price


def _opposite_side(side: Side) -> Side:
    if side == Side.LONG:
        return Side.SHORT
    if side == Side.SHORT:
        return Side.LONG
    return Side.FLAT


def _calc_pnl(side: Side, qty: float, entry_price: float, exit_price: float) -> float:
    if side == Side.LONG:
        return (exit_price - entry_price) * qty
    if side == Side.SHORT:
        return (entry_price - exit_price) * qty
    return 0.0


def _resolve_time(df: pd.DataFrame, idx: int) -> datetime:
    if isinstance(df.index, pd.DatetimeIndex):
        return df.index[idx].to_pydatetime()
    if "timestamp" in df.columns:
        return pd.to_datetime(df["timestamp"].iat[idx]).to_pydatetime()
    return datetime.utcfromtimestamp(idx)


def _empty_trades() -> pd.DataFrame:
    return pd.DataFrame(columns=TRADE_LOG_COLUMNS)


__all__ = ["BacktestOrchestrator"]
