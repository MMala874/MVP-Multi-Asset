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

    def _finalize_datetime_index(frame: pd.DataFrame, dt_values: pd.Series | pd.DatetimeIndex) -> pd.DataFrame:
        idx = pd.DatetimeIndex(dt_values)
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        else:
            idx = idx.tz_convert("UTC")
        idx = idx.rename("timestamp")
        frame.index = idx
        frame = frame[~frame.index.duplicated(keep="last")]
        return frame.sort_index()

    if isinstance(out.index, pd.DatetimeIndex):
        return _finalize_datetime_index(out, out.index)

    col_lookup = {str(c).lower(): c for c in out.columns}
    candidate_names = [col_lookup[c.lower()] for c in prefer_cols if c.lower() in col_lookup]
    candidate_sources: list[tuple[str, pd.Series]] = [(c, out[c]) for c in candidate_names]
    candidate_sources.append(("index", pd.Series(out.index, index=out.index)))

    for source_name, values in candidate_sources:
        dt = pd.to_datetime(values, utc=True, errors="coerce")
        nat_ratio = float(dt.isna().mean()) if len(dt) else 0.0
        if nat_ratio <= 0.01:
            if source_name != "index":
                out = out.loc[dt.notna()].copy()
                dt = dt.loc[dt.notna()]
            return _finalize_datetime_index(out, dt)

    expected = "/".join(prefer_cols)
    raise ValueError(f"No datetime column found (expected one of: {expected})")
