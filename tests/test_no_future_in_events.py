from __future__ import annotations

from pathlib import Path

import pandas as pd

from edge_discovery.event_dataset import load_ohlc_csv
from edge_discovery.events import build_event_matrix


def _write_synthetic_csv(path: Path, n: int = 320) -> None:
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    base = pd.Series(range(n), dtype="float64")
    drift = (base % 17) * 0.00002
    wave = ((base % 9) - 4.0) * 0.00003
    close = 1.20 + (drift + wave).cumsum()
    open_ = close.shift(1).fillna(close.iloc[0])
    span = 0.00025 + (base % 11) * 0.00002
    high = pd.concat([open_, close], axis=1).max(axis=1) + span
    low = pd.concat([open_, close], axis=1).min(axis=1) - span

    df = pd.DataFrame(
        {
            "time": idx.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "open": open_.to_numpy(),
            "high": high.to_numpy(),
            "low": low.to_numpy(),
            "close": close.to_numpy(),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def test_events_source_has_no_negative_shift() -> None:
    source = Path("edge_discovery/events.py").read_text(encoding="utf-8")
    assert "shift(-" not in source


def test_event_prefix_stability_with_truncated_history(tmp_path: Path) -> None:
    csv_path = tmp_path / "synthetic_ohlc.csv"
    _write_synthetic_csv(csv_path, n=360)

    full = load_ohlc_csv(str(csv_path))
    full_events = build_event_matrix(full)

    m = 240
    truncated = full.iloc[:m].copy()
    trunc_events = build_event_matrix(truncated)

    pd.testing.assert_frame_equal(
        full_events.iloc[:m],
        trunc_events,
        check_dtype=False,
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )
