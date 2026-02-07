from __future__ import annotations

import pandas as pd


PRICE_COLUMNS = ["open", "high", "low", "close"]


def build_continuous_contract(df: pd.DataFrame, roll_rule: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    work = df.copy()
    if "timestamp" not in work.columns:
        raise ValueError("Input dataframe must contain a 'timestamp' column")

    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    work = work.sort_values("timestamp").reset_index(drop=True)

    if "contract" not in work.columns:
        work["active_contract"] = "single_contract"
        return work

    if roll_rule.lower() != "volume":
        raise ValueError("Supported roll rules: volume")

    if "volume" not in work.columns:
        raise ValueError("'volume' column is required for volume-based roll")

    ranked = (
        work.sort_values(["timestamp", "volume"], ascending=[True, False])
        .drop_duplicates(subset=["timestamp"], keep="first")
        .rename(columns={"contract": "active_contract"})
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    for col in PRICE_COLUMNS:
        if col in ranked.columns:
            ranked[col] = pd.to_numeric(ranked[col], errors="coerce")

    return ranked
