from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

from configs.models import Config
from execution.cost_model import CostModel
from execution.fill_rules import get_fill_price
from features.indicators import adx, atr, ema, slope
from features.regime import atr_pct_zscore, compute_atr_pct, spike_flag
from risk.allocator import RiskAllocator
from risk.conflict import resolve_conflicts

from backtest.metrics import compute_metrics
from backtest.report import build_report
from backtest.trade_log import TRADE_LOG_COLUMNS
from desk_types import Scenario, Side

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
        prepared = _prepare_features(df_by_symbol, strategies, config)

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
            z_low=config.regime.z_low,
            z_high=config.regime.z_high,
            spike_th=config.regime.spike_tr_atr_th,
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
        slope_window = int(spec.params.get("slope_window", 20))
        z_window = int(spec.params.get("z_window", 30))
        if "ema_base" not in df:
            df["ema_base"] = ema(df["close"], ema_base)
        if "ema_slope" not in df:
            df["ema_slope"] = slope(df["ema_base"], slope_window)
        if "adx" not in df:
            df["adx"] = adx(df, adx_period)
        if "mr_delta" not in df:
            df["mr_delta"] = df["close"] - df["ema_base"]
        if "mr_z" not in df:
            rolling = df["mr_delta"].rolling(window=z_window, min_periods=z_window)
            mean = rolling.mean()
            std = rolling.std(ddof=0)
            df["mr_z"] = (df["mr_delta"] - mean) / std
            df.loc[std == 0, "mr_z"] = np.nan
    elif spec.name == "S3_BREAKOUT_ATR_REGIME_EMA200":
        atr_period = int(spec.params.get("atr_period", 14))
        ema_period = int(spec.params.get("ema200", 200))
        compression_window = int(spec.params.get("compression_window", 50))
        breakout_window = int(spec.params.get("breakout_window", 20))
        if "atr" not in df:
            df["atr"] = atr(df, atr_period)
        if "ema200" not in df:
            df["ema200"] = ema(df["close"], ema_period)
        if "atr_pct" not in df:
            df["atr_pct"] = df["atr"] / df["close"] * 100
        if "compression_z" not in df:
            df["compression_z"] = atr_pct_zscore(df["atr_pct"], window=compression_window)
        if "breakout_high" not in df:
            df["breakout_high"] = (
                df["high"].shift(1).rolling(window=breakout_window, min_periods=breakout_window).max()
            )
        if "breakout_low" not in df:
            df["breakout_low"] = (
                df["low"].shift(1).rolling(window=breakout_window, min_periods=breakout_window).min()
            )
    return df


def _compute_regime(
    df: pd.DataFrame,
    window: int,
    atr_n: int,
    z_low: float = -0.5,
    z_high: float = 0.5,
    spike_th: float = 2.5,
) -> pd.Series:
    atr_pct = compute_atr_pct(df, atr_n=atr_n)
    z = atr_pct_zscore(atr_pct, window=window)

    regime = pd.Series(["UNKNOWN"] * len(df), index=df.index)
    valid_mask = z.notna()
    if valid_mask.any():
        regime.loc[valid_mask] = np.where(
            z[valid_mask] < z_low,
            "LOW",
            np.where(z[valid_mask] > z_high, "HIGH", "MID"),
        )

    if "tr_atr" in df.columns:
        tr_atr = df["tr_atr"]
    else:
        atr_series = atr(df, atr_n)
        prev_close = df["close"].shift(1)
        tr = pd.concat(
            [
                df["high"] - df["low"],
                (df["high"] - prev_close).abs(),
                (df["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        tr_atr = tr / atr_series

    spikes = spike_flag(tr_atr, th=spike_th)
    spike_tag = spikes.astype(int).astype(str)

    return "VOL=" + regime + "|SPIKE=" + spike_tag


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
        cols = {col: df[col].to_numpy() for col in df.columns}
        if "time" not in cols:
            if "timestamp" in df.columns:
                cols["time"] = df["timestamp"].to_numpy()
            elif isinstance(df.index, pd.DatetimeIndex):
                cols["time"] = df.index.to_numpy()
        for idx in range(len(df) - 1):
            signal_time = _resolve_time(df, idx)
            signals = []
            for spec in strategies:
                now_time = signal_time
                ctx = {
                    "cols": cols,
                    "idx": idx,
                    "symbol": symbol,
                    "current_time": signal_time,
                    "now_time": now_time,
                    "regime_snapshot": cols["regime_snapshot"][idx],
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
