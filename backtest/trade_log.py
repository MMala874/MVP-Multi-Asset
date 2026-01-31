from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class TradeLogSchema:
    columns: List[str]


TRADE_LOG_COLUMNS = [
    "trade_id",
    "order_id",
    "symbol",
    "strategy_id",
    "side",
    "qty",
    "signal_time",
    "signal_idx",
    "fill_time",
    "entry_price",
    "exit_time",
    "exit_price",
    "pnl",
    "pnl_pct",
    "spread_used",
    "slippage_used",
    "scenario",
    "regime_snapshot",
    "reason_codes",
    "exit_reason",
    "sl_price",
    "tp_price",
    "gross_pips",
    "cost_pips",
    "pnl_pips",
]

SCHEMA = TradeLogSchema(columns=list(TRADE_LOG_COLUMNS))

__all__ = ["TRADE_LOG_COLUMNS", "SCHEMA", "TradeLogSchema"]
