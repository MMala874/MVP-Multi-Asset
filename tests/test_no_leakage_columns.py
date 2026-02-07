from __future__ import annotations

import pandas as pd

from edge_discovery.event_dataset import build_event_dataset


FORBIDDEN = ("fwd", "mfe", "mae", "resolution", "outcome", "future", "next", "tp", "sl")


def test_event_dataset_has_no_forbidden_columns() -> None:
    idx = pd.date_range("2021-01-01", periods=1000, freq="15min", tz="UTC")
    base = 1.20 + (pd.Series(range(len(idx)), index=idx) * 0.0)
    df = pd.DataFrame(
        {
            "open": base + 0.0001,
            "high": base + 0.0005,
            "low": base - 0.0005,
            "close": base,
        },
        index=idx,
    )

    ds = build_event_dataset(df, event="all", tp_atr=1.5, sl_atr=1.0, horizon=20, min_event_coverage=0.0, max_event_coverage=1.0)
    bad = [c for c in ds.columns if any(tok in c.lower() for tok in FORBIDDEN)]
    assert not bad, f"Forbidden columns present: {bad}"
