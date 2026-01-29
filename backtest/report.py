from __future__ import annotations

from typing import Dict

import pandas as pd


def build_report(trades: pd.DataFrame, metrics: Dict[str, object]) -> Dict[str, object]:
    summary = {
        "total_trades": int(len(trades)),
        "symbols": sorted(trades["symbol"].unique().tolist()) if not trades.empty else [],
        "strategies": sorted(trades["strategy_id"].unique().tolist()) if not trades.empty else [],
        "scenarios": sorted(trades["scenario"].unique().tolist()) if not trades.empty else [],
    }
    return {"summary": summary, "metrics": metrics}


__all__ = ["build_report"]
