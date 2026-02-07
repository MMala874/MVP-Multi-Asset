from __future__ import annotations

import numpy as np
import pandas as pd

from edge_discovery.dataset_builder import build_research_dataset
from edge_discovery.event_dataset import build_event_dataset, save_dataset


FORBIDDEN_TOKENS = (
    "fwd",
    "mfe",
    "mae",
    "future",
    "next",
    "resolution",
    "outcome",
    "tp",
    "sl",
    "bars_to_resolution",
    "outcome_type",
    "diag_",
)


def _assert_no_forbidden_columns(df: pd.DataFrame) -> None:
    bad = [c for c in df.columns if any(tok in c.lower() for tok in FORBIDDEN_TOKENS)]
    assert not bad, f"Forbidden columns present: {bad}"


def _make_ohlc(n: int = 6000) -> pd.DataFrame:
    rng = np.random.default_rng(123)
    idx = pd.date_range("2021-01-01", periods=n, freq="15min", tz="UTC")
    close = 1.10 + np.cumsum(rng.normal(0.0, 0.00045, n))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    spread = rng.uniform(0.00005, 0.00060, n)
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread,
            "close": close,
            "volume": rng.integers(50, 600, n),
        },
        index=idx,
    )


def test_research_dataset_export_has_no_forbidden_columns(tmp_path) -> None:
    df = _make_ohlc()
    out_dir = tmp_path / "research"
    build_research_dataset(df, out_dir=out_dir)

    research_path = out_dir / "research_dataset_v2.csv"
    research = pd.read_csv(research_path)
    _assert_no_forbidden_columns(research)


def test_event_dataset_export_has_no_forbidden_columns(tmp_path) -> None:
    df = _make_ohlc()
    ds = build_event_dataset(df, event="all", tp_atr=1.5, sl_atr=1.0, horizon=20, min_event_coverage=0.0, max_event_coverage=1.0)

    event_path = tmp_path / "event_ds_test.csv"
    save_dataset(ds, str(event_path))

    event_df = pd.read_csv(event_path)
    _assert_no_forbidden_columns(event_df)


def test_event_dataset_range_expansion_mode_has_no_forbidden_columns(tmp_path) -> None:
    df = _make_ohlc()
    ds = build_event_dataset(
        df,
        event="vol_compress_expand",
        tp_atr=1.5,
        sl_atr=1.0,
        horizon=20,
        min_event_coverage=0.0,
        max_event_coverage=1.0,
        label_mode="range_expansion",
        range_k=2.0,
        event_config={"compress_window": 96, "compress_q": 0.1},
    )

    event_path = tmp_path / "event_ds_range_expansion_test.csv"
    save_dataset(ds, str(event_path))

    event_df = pd.read_csv(event_path)
    _assert_no_forbidden_columns(event_df)
