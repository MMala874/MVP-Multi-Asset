from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _hour_utc(df: pd.DataFrame) -> pd.Series:
    if "hour" in df.columns:
        return pd.to_numeric(df["hour"], errors="coerce")
    if "timestamp" in df.columns:
        return pd.to_datetime(df["timestamp"], utc=True, errors="coerce").dt.hour
    raise ValueError("Need either 'hour' or 'timestamp' column for london filter")


def filter_london(df: pd.DataFrame, hour_start: int = 7, hour_end: int = 16) -> pd.Series:
    h = _hour_utc(df)
    return h.between(hour_start, hour_end, inclusive="both").fillna(False)


def filter_high_vol(df: pd.DataFrame, min_atr_ratio: float = 1.1) -> pd.Series:
    if "atr_ratio" not in df.columns:
        return pd.Series(False, index=df.index)
    return pd.to_numeric(df["atr_ratio"], errors="coerce").ge(min_atr_ratio).fillna(False)


def filter_compression(df: pd.DataFrame, max_vol_z20: float = 0.0, quantile: float | None = None) -> pd.Series:
    if "vol_z20" not in df.columns:
        return pd.Series(False, index=df.index)
    vals = pd.to_numeric(df["vol_z20"], errors="coerce")
    thr = float(vals.quantile(quantile)) if quantile is not None else float(max_vol_z20)
    return vals.lt(thr).fillna(False)


def filter_near_pdh(df: pd.DataFrame, max_dist_z: float = 0.5) -> pd.Series:
    col = "dist_prev_day_high_z"
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").abs().le(max_dist_z).fillna(False)


def filter_near_pdl(df: pd.DataFrame, max_dist_z: float = 0.5) -> pd.Series:
    col = "dist_prev_day_low_z"
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").abs().le(max_dist_z).fillna(False)


def filter_position(df: pd.DataFrame, lo: float = 0.2, hi: float = 0.8) -> pd.Series:
    if "pos_in_range50" not in df.columns:
        return pd.Series(False, index=df.index)
    vals = pd.to_numeric(df["pos_in_range50"], errors="coerce")
    return vals.between(lo, hi, inclusive="both").fillna(False)


def filter_trend_quality(df: pd.DataFrame, min_reg_r2_20: float = 0.2) -> pd.Series:
    if "reg_r2_20" not in df.columns:
        return pd.Series(False, index=df.index)
    return pd.to_numeric(df["reg_r2_20"], errors="coerce").ge(min_reg_r2_20).fillna(False)


def apply_filter_pack(df: pd.DataFrame, pack: dict[str, Any]) -> tuple[pd.DataFrame, pd.Series, dict[str, Any]]:
    mask = pd.Series(True, index=df.index)
    stats: dict[str, Any] = {"active_filters": {}, "n_in": int(len(df))}

    def _apply(name: str, local_mask: pd.Series) -> None:
        nonlocal mask
        mask &= local_mask
        stats["active_filters"][name] = float(local_mask.mean())

    for key, cfg in pack.items():
        if cfg is False or cfg is None:
            continue
        params = cfg if isinstance(cfg, dict) else {}
        if key == "london":
            _apply(key, filter_london(df, **params))
        elif key == "high_vol":
            _apply(key, filter_high_vol(df, **params))
        elif key == "compression":
            _apply(key, filter_compression(df, **params))
        elif key == "near_pdh":
            _apply(key, filter_near_pdh(df, **params))
        elif key == "near_pdl":
            _apply(key, filter_near_pdl(df, **params))
        elif key == "position":
            _apply(key, filter_position(df, **params))
        elif key == "trend_quality":
            _apply(key, filter_trend_quality(df, **params))

    filtered = df.loc[mask].copy()
    stats["n_out"] = int(len(filtered))
    stats["retention"] = float(stats["n_out"] / stats["n_in"]) if stats["n_in"] > 0 else float("nan")
    return filtered, mask, stats
