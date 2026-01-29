from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import pandas as pd


@dataclass(frozen=True)
class HealthSummary:
    strategy_id: str
    total_trades: int
    recent_trades: int
    win_rate: float
    avg_pnl: float
    pnl_sum: float
    pnl_pct_mean: float | None
    flag: str


def compute_health_metrics(
    trades_df: pd.DataFrame,
    reference_stats: Dict[str, Dict[str, Any]] | None = None,
    window: int = 30,
) -> Dict[str, Dict[str, Any]]:
    if trades_df is None or trades_df.empty:
        return {}

    reference_stats = reference_stats or {}
    output: Dict[str, Dict[str, Any]] = {}
    strategies = trades_df["strategy_id"].dropna().unique()

    for strategy_id in strategies:
        strategy_trades = trades_df[trades_df["strategy_id"] == strategy_id]
        if strategy_trades.empty:
            continue

        ordered = _order_trades(strategy_trades)
        recent = ordered.tail(window)
        summary = _build_summary(strategy_id, ordered, recent, reference_stats.get(strategy_id))
        output[strategy_id] = summary.__dict__.copy()

    return output


def _order_trades(trades: pd.DataFrame) -> pd.DataFrame:
    for column in ("fill_time", "exit_time", "signal_time"):
        if column in trades.columns:
            return trades.sort_values(column)
    return trades.sort_index()


def _build_summary(
    strategy_id: str,
    all_trades: pd.DataFrame,
    recent_trades: pd.DataFrame,
    reference: Dict[str, Any] | None,
) -> HealthSummary:
    total_trades = int(all_trades.shape[0])
    recent_count = int(recent_trades.shape[0])
    win_rate = _win_rate(recent_trades)
    avg_pnl = _avg_pnl(recent_trades)
    pnl_sum = float(recent_trades["pnl"].sum()) if "pnl" in recent_trades.columns else 0.0
    pnl_pct_mean = _pnl_pct_mean(recent_trades)
    flag = _flag_status(
        recent_count=recent_count,
        win_rate=win_rate,
        avg_pnl=avg_pnl,
        reference=reference,
        all_trades=all_trades,
    )

    return HealthSummary(
        strategy_id=strategy_id,
        total_trades=total_trades,
        recent_trades=recent_count,
        win_rate=win_rate,
        avg_pnl=avg_pnl,
        pnl_sum=pnl_sum,
        pnl_pct_mean=pnl_pct_mean,
        flag=flag,
    )


def _win_rate(trades: pd.DataFrame) -> float:
    if trades.empty or "pnl" not in trades.columns:
        return 0.0
    wins = (trades["pnl"] > 0).sum()
    return float(wins) / float(len(trades))


def _avg_pnl(trades: pd.DataFrame) -> float:
    if trades.empty or "pnl" not in trades.columns:
        return 0.0
    return float(trades["pnl"].mean())


def _pnl_pct_mean(trades: pd.DataFrame) -> float | None:
    if trades.empty or "pnl_pct" not in trades.columns:
        return None
    return float(trades["pnl_pct"].mean())


def _flag_status(
    *,
    recent_count: int,
    win_rate: float,
    avg_pnl: float,
    reference: Dict[str, Any] | None,
    all_trades: pd.DataFrame,
) -> str:
    if recent_count == 0:
        return "OUT_OF_PROFILE"

    baseline = reference or {}
    baseline_win_rate = baseline.get("win_rate")
    baseline_avg_pnl = baseline.get("avg_pnl")

    if baseline_win_rate is None or baseline_avg_pnl is None:
        baseline_win_rate = _win_rate(all_trades)
        baseline_avg_pnl = _avg_pnl(all_trades)

    if baseline_win_rate == 0 and baseline_avg_pnl == 0:
        return "OK"

    win_rate_drop = win_rate < baseline_win_rate * 0.7
    avg_pnl_drop = avg_pnl < baseline_avg_pnl * 0.7 if baseline_avg_pnl >= 0 else avg_pnl < baseline_avg_pnl * 1.3

    if avg_pnl < 0 and baseline_avg_pnl >= 0 and win_rate < baseline_win_rate:
        return "OUT_OF_PROFILE"
    if win_rate_drop or avg_pnl_drop:
        return "WEAKENING"
    return "OK"
