from __future__ import annotations

import pandas as pd


def ensure_datetime_index(
    df: pd.DataFrame,
    *,
    prefer_cols: tuple[str, ...] = ("timestamp", "time", "datetime", "date"),
) -> pd.DataFrame:
    """Return a copy of ``df`` with a validated DatetimeIndex.

    Priority order:
    1) existing DatetimeIndex
    2) first valid column in ``prefer_cols``
    3) parsed ``df.index`` fallback

    A candidate is considered valid when NaT ratio is <= 1%.
    """
    out = df.copy()

    if isinstance(out.index, pd.DatetimeIndex):
        return out

    candidate_names = [c for c in prefer_cols if c in out.columns]
    candidate_sources: list[tuple[str, pd.Series]] = [(c, out[c]) for c in candidate_names]
    candidate_sources.append(("index", pd.Series(out.index, index=out.index)))

    for source_name, values in candidate_sources:
        dt = pd.to_datetime(values, utc=True, errors="coerce")
        nat_ratio = float(dt.isna().mean()) if len(dt) else 0.0
        if nat_ratio <= 0.01:
            if source_name != "index":
                out = out.loc[dt.notna()].copy()
                dt = dt.loc[dt.notna()]
            out.index = pd.DatetimeIndex(dt)
            return out.sort_index()

    expected = "/".join(prefer_cols)
    raise ValueError(f"No datetime column found (expected one of: {expected})")

