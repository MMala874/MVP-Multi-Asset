from __future__ import annotations

import pandas as pd

from edge_discovery.events import event_prev_day_sweep_reclaim


def test_event_prev_day_sweep_reclaim_accepts_time_column_without_datetime_index() -> None:
    n = 240
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    base = pd.Series(range(n), dtype="float64")
    close = 1.10 + ((base % 12) - 6.0).cumsum() * 0.00005
    open_ = close.shift(1).fillna(close.iloc[0])
    spread = 0.0002 + (base % 5) * 0.00003
    high = pd.concat([open_, close], axis=1).max(axis=1) + spread
    low = pd.concat([open_, close], axis=1).min(axis=1) - spread

    df = pd.DataFrame(
        {
            "time": idx.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "open": open_.to_numpy(),
            "high": high.to_numpy(),
            "low": low.to_numpy(),
            "close": close.to_numpy(),
        }
    )

    events = event_prev_day_sweep_reclaim(df)

    assert len(events) == len(df)
    assert events.dtype == bool

