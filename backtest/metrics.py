from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def compute_metrics(trades: pd.DataFrame) -> Dict[str, object]:
    if trades.empty:
        return {
            "overall": _empty_metrics(),
            "by_strategy": {},
            "by_symbol": {},
            "by_regime": {},
            "by_scenario": {},
        }

    overall = _calc_metrics(trades)
    return {
        "overall": overall,
        "by_strategy": _group_metrics(trades, "strategy_id"),
        "by_symbol": _group_metrics(trades, "symbol"),
        "by_regime": _group_metrics(trades, "regime_snapshot"),
        "by_scenario": _group_metrics(trades, "scenario"),
    }


def _group_metrics(trades: pd.DataFrame, column: str) -> Dict[str, Dict[str, float]]:
    grouped: Dict[str, Dict[str, float]] = {}
    for key, group in trades.groupby(column):
        grouped[str(key)] = _calc_metrics(group)
    return grouped


def _calc_metrics(trades: pd.DataFrame) -> Dict[str, float]:
    pnl = trades["pnl"].astype(float)
    expectancy = float(pnl.mean()) if not pnl.empty else 0.0

    gains = pnl[pnl > 0].sum()
    losses = pnl[pnl < 0].sum()
    profit_factor = float(gains / abs(losses)) if losses != 0 else float("inf") if gains > 0 else 0.0

    cumulative = pnl.cumsum()
    drawdown = cumulative - cumulative.cummax()
    max_dd = float(drawdown.min()) if not drawdown.empty else 0.0

    cvar = _cvar(pnl)

    win_streak, loss_streak = _streaks(pnl)

    return {
        "trades": float(len(pnl)),
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "max_drawdown": max_dd,
        "cvar_95": cvar,
        "max_win_streak": float(win_streak),
        "max_loss_streak": float(loss_streak),
    }


def _cvar(pnl: pd.Series, alpha: float = 0.95) -> float:
    if pnl.empty:
        return 0.0
    sorted_pnl = pnl.sort_values()
    cutoff = int(np.ceil((1 - alpha) * len(sorted_pnl)))
    if cutoff <= 0:
        return 0.0
    tail = sorted_pnl.iloc[:cutoff]
    return float(tail.mean()) if not tail.empty else 0.0


def _streaks(pnl: pd.Series) -> tuple[int, int]:
    max_win = 0
    max_loss = 0
    current_win = 0
    current_loss = 0

    for value in pnl:
        if value > 0:
            current_win += 1
            current_loss = 0
        elif value < 0:
            current_loss += 1
            current_win = 0
        else:
            current_win = 0
            current_loss = 0
        max_win = max(max_win, current_win)
        max_loss = max(max_loss, current_loss)

    return max_win, max_loss


def _empty_metrics() -> Dict[str, float]:
    return {
        "trades": 0.0,
        "expectancy": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 0.0,
        "cvar_95": 0.0,
        "max_win_streak": 0.0,
        "max_loss_streak": 0.0,
    }
