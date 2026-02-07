from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def validate_data(df: pd.DataFrame) -> dict:
    report = {
        "rows": int(len(df)),
        "missing_ratio": 1.0,
        "missing_minutes": 0,
        "expected_minutes": 0,
        "duplicate_timestamps": 0,
        "null_counts": {},
        "rolls": 0,
        "passes_missing_threshold": False,
    }

    if df.empty:
        return report

    work = df.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    work = work.sort_values("timestamp")

    full_idx = pd.date_range(work["timestamp"].min(), work["timestamp"].max(), freq="1min", tz="UTC")
    observed = pd.DatetimeIndex(work["timestamp"])

    missing_minutes = len(full_idx.difference(observed))
    expected_minutes = len(full_idx)
    missing_ratio = missing_minutes / expected_minutes if expected_minutes else 0.0

    rolls = 0
    if "active_contract" in work.columns:
        rolls = int(work["active_contract"].ne(work["active_contract"].shift(1)).sum() - 1)
        rolls = max(rolls, 0)

    report.update(
        {
            "missing_ratio": float(missing_ratio),
            "missing_minutes": int(missing_minutes),
            "expected_minutes": int(expected_minutes),
            "duplicate_timestamps": int(work.duplicated(subset=["timestamp"]).sum()),
            "null_counts": {k: int(v) for k, v in work.isna().sum().items()},
            "rolls": rolls,
            "passes_missing_threshold": bool(missing_ratio < 0.001),
        }
    )
    return report


def save_quality_report(report: dict, path: str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
