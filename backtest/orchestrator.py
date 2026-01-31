from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

from configs.models import Config
from data.fx import PIP_SIZES, to_price
from execution.cost_model import CostModel
from execution.fill_rules import get_fill_price
from features.indicators import adx, atr, ema, slope
from features.regime import atr_pct_zscore, compute_atr_pct, spike_flag
from risk.allocator import RiskAllocator, _build_state, _estimate_usd_exposure, _resolve_risk_multiplier, _within_caps
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

        pip_size = PIP_SIZES.get(symbol, 0.0001)
        if "atr_pips" not in df_local:
            df_local["atr_pips"] = df_local["atr"] / pip_size


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
    debug_enabled = bool(getattr(config.outputs, "debug", False))
    strategy_counts = _init_strategy_debug_counts(strategies) if debug_enabled else {}
    order_debug = _init_order_debug_counts() if debug_enabled else {}

    trades: List[Dict[str, Any]] = []
    trade_id = 1

    for symbol, df in df_by_symbol.items():
        position = {
            "current_side": Side.FLAT,
            "entry_price": None,
            "entry_time": None,
            "entry_idx": None,
            "entry_price_adj": None,
            "qty": None,
            "strategy_id": None,
            "signal_time": None,
            "signal_idx": None,
            "sl_price": None,
            "tp_price": None,
            "spread_used": None,
            "slippage_used": None,
            "entry_cost_pips": None,
            "exit_cost_pips": None,
            "reason_codes": None,
        }
        cols = {col: df[col].to_numpy() for col in df.columns}
        if "time" not in cols:
            if "timestamp" in df.columns:
                cols["time"] = df["timestamp"].to_numpy()
            elif isinstance(df.index, pd.DatetimeIndex):
                cols["time"] = df.index.to_numpy()
        for idx in range(len(df) - 1):
            if position["current_side"] != Side.FLAT:
                exit_price_raw = None
                exit_time = _resolve_time(df, idx + 1)
                high = float(df["high"].iat[idx + 1])
                low = float(df["low"].iat[idx + 1])
                if position["current_side"] == Side.LONG:
                    sl_price = position["sl_price"]
                    tp_price = position["tp_price"]
                    sl_hit = sl_price is not None and low <= sl_price
                    tp_hit = tp_price is not None and high >= tp_price
                    if sl_hit:
                        exit_price_raw = sl_price
                    elif tp_hit:
                        exit_price_raw = tp_price
                elif position["current_side"] == Side.SHORT:
                    sl_price = position["sl_price"]
                    tp_price = position["tp_price"]
                    sl_hit = sl_price is not None and high >= sl_price
                    tp_hit = tp_price is not None and low <= tp_price
                    if sl_hit:
                        exit_price_raw = sl_price
                    elif tp_hit:
                        exit_price_raw = tp_price
                # Check TIME stop (max hold bars exceeded)
                if exit_price_raw is None:
                    held_bars = (idx + 1) - position["entry_idx"]
                    max_hold_bars = config.risk.max_hold_bars
                    if held_bars >= max_hold_bars:
                        exit_price_raw = float(df["close"].iat[idx + 1])
                # End-of-data exit
                if exit_price_raw is None and (idx + 1) == (len(df) - 1):
                    exit_price_raw = float(df["close"].iat[idx + 1])

                if exit_price_raw is not None:
                    exit_cost = cost_model.trade_cost_pips(
                        symbol=symbol,
                        idx_t=idx,
                        scenario=scenario,
                        df=df,
                        atr_series=df["atr"],
                    )[1]
                    position["exit_cost_pips"] = exit_cost
                    exit_price_raw = float(exit_price_raw)
                    exit_price_adj = _apply_cost(
                        exit_price_raw,
                        exit_cost,
                        _opposite_side(position["current_side"]),
                        symbol,
                    )
                    assert exit_price_raw > 0
                    assert exit_price_adj > 0
                    pnl = _calc_pnl(
                        position["current_side"],
                        float(position["qty"]),
                        float(position["entry_price_adj"]),
                        exit_price_adj,
                    )
                    pnl_pct = (
                        pnl / (abs(position["entry_price_adj"]) * abs(position["qty"]))
                        if position["qty"] != 0
                        else 0.0
                    )
                    exit_reason = "EOD"
                    if position["current_side"] == Side.LONG:
                        if sl_hit: exit_reason = "SL"
                        elif tp_hit: exit_reason = "TP"
                        else:
                            held_bars = (idx + 1) - position["entry_idx"]
                            if held_bars >= config.risk.max_hold_bars:
                                exit_reason = "TIME"
                    elif position["current_side"] == Side.SHORT:
                        if sl_hit: exit_reason = "SL"
                        elif tp_hit: exit_reason = "TP"
                        else:
                            held_bars = (idx + 1) - position["entry_idx"]
                            if held_bars >= config.risk.max_hold_bars:
                                exit_reason = "TIME"

                    pip = PIP_SIZES.get(symbol, 0.0001)
                    pip_size = PIP_SIZES.get(symbol, 0.0001)

                    entry_raw = float(position["entry_price"])
                    exit_raw = float(exit_price_raw)

                    if position["current_side"] == Side.LONG:
                        gross_pips = (exit_raw - entry_raw) / pip_size
                    elif position["current_side"] == Side.SHORT:
                        gross_pips = (entry_raw - exit_raw) / pip_size
                    else:
                        gross_pips = 0.0

                    entry_cost_pips = float(position["entry_cost_pips"]) if position["entry_cost_pips"] is not None else 0.0
                    exit_cost_pips = float(position["exit_cost_pips"]) if position["exit_cost_pips"] is not None else 0.0
                    cost_pips = entry_cost_pips + exit_cost_pips
                    pnl_pips = gross_pips - cost_pips


                    trades.append(
                        {
                            "trade_id": trade_id,
                            "order_id": f"{scenario}-{symbol}-{position['entry_idx']}-{trade_id}",
                            "symbol": symbol,
                            "strategy_id": position["strategy_id"],
                            "side": position["current_side"].value,
                            "qty": position["qty"],
                            "signal_time": position["signal_time"],
                            "signal_idx": position["signal_idx"],
                            "fill_time": position["entry_time"],
                            "entry_price": position["entry_price_adj"],
                            "exit_time": exit_time,
                            "exit_price": exit_price_adj,
                            "pnl": pnl,
                            "pnl_pct": pnl_pct,
                            "spread_used": position["spread_used"],
                            "slippage_used": position["slippage_used"],
                            "scenario": scenario,
                            "regime_snapshot": df["regime_snapshot"].iat[idx],
                            "reason_codes": position["reason_codes"],
                            "exit_reason": exit_reason,
                            "sl_price": position["sl_price"],
                            "tp_price": position["tp_price"],
                            "gross_pips": gross_pips,
                            "cost_pips": cost_pips,
                            "pnl_pips": pnl_pips,

                        }
                    )
                    trade_id += 1
                    position = {
                        "current_side": Side.FLAT,
                        "entry_price": None,
                        "entry_time": None,
                        "entry_idx": None,
                        "entry_price_adj": None,
                        "qty": None,
                        "strategy_id": None,
                        "signal_time": None,
                        "signal_idx": None,
                        "sl_price": None,
                        "tp_price": None,
                        "spread_used": None,
                        "slippage_used": None,
                        "reason_codes": None,
                    }
                continue
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
                if debug_enabled:
                    _update_strategy_debug_counts(strategy_counts, signal, spec, cols, idx)
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
            if debug_enabled:
                _update_order_debug_counts(filtered, state, config, order_debug)
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
                entry_price_adj = _apply_cost(entry_price, entry_cost, order.side, symbol)
                base_price = entry_price_adj
                assert entry_price > 0
                assert entry_price_adj > 0
                reason_codes = _encode_reason_codes(order.meta, filtered)
                sl_price = None
                tp_price = None

                base_price = entry_price_adj

                if order.sl_points is not None:
                    sl_dist_price = to_price(symbol, float(order.sl_points))
                    if order.side == Side.LONG:
                        sl_price = base_price - sl_dist_price
                    elif order.side == Side.SHORT:
                        sl_price = base_price + sl_dist_price

                if order.tp_points is not None:
                    tp_dist_price = to_price(symbol, float(order.tp_points))
                    if order.side == Side.LONG:
                        tp_price = base_price + tp_dist_price
                    elif order.side == Side.SHORT:
                        tp_price = base_price - tp_dist_price

                position = {
                    "current_side": order.side,
                    "entry_price": entry_price,
                    "entry_time": _resolve_time(df, idx + 1),
                    "entry_idx": idx,
                    "entry_price_adj": entry_price_adj,
                    "qty": order.qty,
                    "strategy_id": order.strategy_id,
                    "signal_time": signal_time,
                    "signal_idx": idx,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "spread_used": spread_used,
                    "slippage_used": slippage_used,
                    "entry_cost_pips": entry_cost,
                    "exit_cost_pips": None,
                    "reason_codes": reason_codes,
                }
                break

    trades_df = pd.DataFrame(trades, columns=TRADE_LOG_COLUMNS)
    if debug_enabled:
        _print_scenario_debug_summary(scenario, strategy_counts, order_debug)
    return trades_df


def _encode_reason_codes(meta: Dict[str, str], signals: Iterable[Any]) -> str:
    codes = []
    for signal in signals:
        for key, value in signal.tags.items():
            codes.append(f"{key}={value}")
    for key, value in meta.items():
        codes.append(f"{key}={value}")
    return ";".join(codes)


def _apply_cost(price: float, cost: float, side: Side, symbol: str) -> float:
    cost_price = to_price(symbol, cost)
    if side == Side.LONG:
        price_adj = price + cost_price
    elif side == Side.SHORT:
        price_adj = price - cost_price
    else:
        price_adj = price
    if symbol in PIP_SIZES:
        assert price_adj > 0
        assert price > 0
    return price_adj


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
    if "time" in df.columns:
        return pd.to_datetime(df["time"].iat[idx]).to_pydatetime()
    if isinstance(df.index, pd.DatetimeIndex):
        return df.index[idx].to_pydatetime()
    return datetime.utcfromtimestamp(idx)


def _empty_trades() -> pd.DataFrame:
    return pd.DataFrame(columns=TRADE_LOG_COLUMNS)


def _new_strategy_debug_counts() -> Dict[str, int]:
    return {"n_long": 0, "n_short": 0, "n_flat": 0, "n_nan_skip": 0}


def _init_strategy_debug_counts(strategies: Iterable[_StrategySpec]) -> Dict[str, Dict[str, int]]:
    counts: Dict[str, Dict[str, int]] = {}
    for spec in strategies:
        strategy_id = getattr(spec.module, "STRATEGY_ID", spec.name)
        counts[strategy_id] = _new_strategy_debug_counts()
    return counts


def _strategy_has_nan(spec: _StrategySpec, cols: Dict[str, np.ndarray], idx: int) -> bool:
    required_features = getattr(spec.module, "required_features", None)
    if not callable(required_features):
        return False
    for feature in required_features():
        values = cols.get(feature)
        if values is None:
            return True
        value = values[idx]
        if value is None:
            return True
        if isinstance(value, (float, np.floating)) and np.isnan(value):
            return True
    return False


def _update_strategy_debug_counts(
    strategy_counts: Dict[str, Dict[str, int]],
    signal: Any,
    spec: _StrategySpec,
    cols: Dict[str, np.ndarray],
    idx: int,
) -> None:
    counts = strategy_counts.setdefault(signal.strategy_id, _new_strategy_debug_counts())
    if signal.side == Side.LONG:
        counts["n_long"] += 1
    elif signal.side == Side.SHORT:
        counts["n_short"] += 1
    else:
        counts["n_flat"] += 1
        if _strategy_has_nan(spec, cols, idx):
            counts["n_nan_skip"] += 1


def _init_order_debug_counts() -> Dict[str, Any]:
    return {
        "created": 0,
        "skipped": {
            "missing_sl_points": 0,
            "nonpositive_sl_points": 0,
            "nonpositive_risk_amount": 0,
            "qty_nonpositive": 0,
            "caps": 0,
        },
    }


def _update_order_debug_counts(
    signals: List[Any],
    state: object | None,
    config: Config,
    order_debug: Dict[str, Any],
) -> None:
    caps = config.risk.caps
    state_view = _build_state(state)
    risk_by_strategy: Dict[str, float] = {}
    risk_by_symbol: Dict[str, float] = {}
    exposure_total = state_view.exposure_total

    for signal in signals:
        if signal.sl_points is None:
            order_debug["skipped"]["missing_sl_points"] += 1
            continue
        if signal.sl_points <= 0:
            order_debug["skipped"]["nonpositive_sl_points"] += 1
            continue

        risk_multiplier = _resolve_risk_multiplier(signal, state_view)
        risk_amount = config.risk.r_base * risk_multiplier
        if risk_amount <= 0:
            order_debug["skipped"]["nonpositive_risk_amount"] += 1
            continue

        qty = risk_amount / signal.sl_points
        if qty <= 0:
            order_debug["skipped"]["qty_nonpositive"] += 1
            continue

        if not _within_caps(
            signal,
            risk_amount,
            qty,
            risk_by_strategy,
            risk_by_symbol,
            caps.per_strategy,
            caps.per_symbol,
            caps.usd_exposure_cap,
            state_view,
            exposure_total,
        ):
            order_debug["skipped"]["caps"] += 1
            continue

        order_debug["created"] += 1
        risk_by_strategy[signal.strategy_id] = risk_by_strategy.get(signal.strategy_id, 0.0) + risk_amount
        risk_by_symbol[signal.symbol] = risk_by_symbol.get(signal.symbol, 0.0) + risk_amount
        exposure_total += _estimate_usd_exposure(qty, signal.symbol, state_view)


def _print_scenario_debug_summary(
    scenario: str,
    strategy_counts: Dict[str, Dict[str, int]],
    order_debug: Dict[str, Any],
) -> None:
    print(f"[debug] Scenario {scenario} summary")
    for strategy_id, counts in sorted(strategy_counts.items()):
        print(
            "[debug]  "
            f"{strategy_id}: long={counts['n_long']} short={counts['n_short']} "
            f"flat={counts['n_flat']} nan_skip={counts['n_nan_skip']}"
        )
    skipped = order_debug["skipped"]
    skipped_total = sum(skipped.values())
    print(
        "[debug]  orders: "
        f"created={order_debug['created']} skipped={skipped_total} "
        "(missing_sl_points={missing_sl_points}, nonpositive_sl_points={nonpositive_sl_points}, "
        "nonpositive_risk_amount={nonpositive_risk_amount}, qty_nonpositive={qty_nonpositive}, "
        "caps={caps})".format(**skipped)
    )


__all__ = ["BacktestOrchestrator"]
