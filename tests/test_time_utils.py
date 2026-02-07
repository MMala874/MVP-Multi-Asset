from __future__ import annotations

import pandas as pd

from edge_discovery.events import event_prev_day_sweep_reclaim
from edge_discovery.time_utils import ensure_datetime_index


def _build_ohlc_with_time_column(n: int = 240) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    base = pd.Series(range(n), dtype="float64")
    close = 1.10 + ((base % 12) - 6.0).cumsum() * 0.00005
    open_ = close.shift(1).fillna(close.iloc[0])
    spread = 0.0002 + (base % 5) * 0.00003
    high = pd.concat([open_, close], axis=1).max(axis=1) + spread
    low = pd.concat([open_, close], axis=1).min(axis=1) - spread

    return pd.DataFrame(
        {
            "time": idx.strftime("%Y-%m-%d %H:%M:%S+00:00"),
            "open": open_.to_numpy(),
            "high": high.to_numpy(),
            "low": low.to_numpy(),
            "close": close.to_numpy(),
        }
    )


def test_ensure_datetime_index_converts_time_column_with_utc_offset() -> None:
    df = _build_ohlc_with_time_column()

    out = ensure_datetime_index(df)

    assert isinstance(out.index, pd.DatetimeIndex)
    assert str(out.index.tz) == "UTC"
    assert out.index.name == "timestamp"
    assert len(out) == len(df)


def test_event_prev_day_sweep_reclaim_accepts_csv_style_time_column() -> None:
    df = _build_ohlc_with_time_column()

    events = event_prev_day_sweep_reclaim(df)

    assert isinstance(events, pd.Series)
    assert events.dtype == bool
    assert events.index.equals(ensure_datetime_index(df).index)
    assert len(events) == len(df)
