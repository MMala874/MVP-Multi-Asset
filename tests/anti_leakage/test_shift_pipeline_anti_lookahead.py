from __future__ import annotations

import numpy as np
import pandas as pd

from edge_discovery.event_engine import compute_event_flags
from edge_discovery.feature_engine import compute_features
from edge_discovery.forward_metrics import compute_forward_metrics


def _make_m15_ohlcv(n: int = 5000, seed: int = 123) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-01-01", periods=n, freq="15min")

    close = 1.10 + np.cumsum(rng.normal(0.0, 0.0003, n))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    spread = rng.uniform(0.00005, 0.0004, n)

    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.integers(50, 400, n)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def test_shift_pipeline_no_lookahead_components() -> None:
    df = _make_m15_ohlcv()
    i = 4200
    h = 20

    events_a = compute_event_flags(df)
    feats_a = compute_features(df)
    fwd_a = compute_forward_metrics(df, horizons=[5, 10, h])

    df2 = df.copy()
    df2.iloc[i + 1 :, df2.columns.get_loc("close")] += 0.02
    df2.iloc[i + 1 :, df2.columns.get_loc("high")] += 0.02
    df2.iloc[i + 1 :, df2.columns.get_loc("low")] += 0.02

    events_b = compute_event_flags(df2)
    feats_b = compute_features(df2)
    fwd_b = compute_forward_metrics(df2, horizons=[5, 10, h])

    pd.testing.assert_frame_equal(events_a.iloc[: i + 1], events_b.iloc[: i + 1], check_dtype=False)
    pd.testing.assert_frame_equal(feats_a.iloc[: i + 1], feats_b.iloc[: i + 1], check_dtype=False)

    # Forward metrics at t are unaffected when [t+1, t+h] does not reach the modified region.
    safe_end = i - h
    pd.testing.assert_frame_equal(
        fwd_a.iloc[: safe_end + 1],
        fwd_b.iloc[: safe_end + 1],
        check_dtype=False,
        check_exact=False,
        rtol=1e-10,
        atol=1e-12,
    )
