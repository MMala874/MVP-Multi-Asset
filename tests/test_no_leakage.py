from __future__ import annotations

import numpy as np
import pandas as pd

from edge_discovery.dataset_builder import build_research_dataset


def _make_ohlc(n: int = 4500) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=n, freq="15min", tz="UTC", name="time")
    rng = np.random.default_rng(42)
    ret = rng.normal(0, 0.0002, size=n)
    close = 1.10 + np.cumsum(ret)
    open_ = np.r_[close[0], close[:-1]]
    span = np.abs(rng.normal(0.00025, 0.00008, size=n))
    high = np.maximum(open_, close) + span
    low = np.minimum(open_, close) - span
    vol = rng.integers(100, 1000, size=n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


def test_no_feature_event_leakage_and_conditional_label_stability() -> None:
    base = _make_ohlc()
    cutoff = base.index[3500]

    ds1 = build_research_dataset(base, config={"horizon": 10})

    modified = base.copy()
    mask_future = modified.index >= cutoff
    modified.loc[mask_future, "close"] *= 1.02
    modified.loc[mask_future, "high"] *= 1.03
    modified.loc[mask_future, "low"] *= 0.97

    ds2 = build_research_dataset(modified, config={"horizon": 10})

    for ds in (ds1, ds2):
        ds["timestamp"] = pd.to_datetime(ds["timestamp"], utc=True)

    pre1 = ds1[ds1["timestamp"] < cutoff].set_index("timestamp")
    pre2 = ds2[ds2["timestamp"] < cutoff].set_index("timestamp")
    common = pre1.index.intersection(pre2.index)
    pre1, pre2 = pre1.loc[common], pre2.loc[common]

    event_cols = [
        "SWEEP_PREV_DAY_HIGH",
        "SWEEP_PREV_DAY_LOW",
        "IMPULSE_BODY",
        "RANGE_COMPRESSION",
        "VOL_REGIME_SHIFT",
        "EXPANSION_BAR",
    ]
    meta_cols = {"label", "bars_to_resolution", "outcome_type"}
    feature_cols = [c for c in pre1.columns if c not in set(event_cols) | meta_cols]

    pd.testing.assert_frame_equal(pre1[event_cols], pre2[event_cols], check_dtype=False)
    pd.testing.assert_frame_equal(pre1[feature_cols], pre2[feature_cols], check_dtype=False, check_exact=False, rtol=1e-7)

    safe_mask = pre1.index + pd.Timedelta(minutes=15 * 10) < cutoff
    pd.testing.assert_series_equal(pre1.loc[safe_mask, "label"], pre2.loc[safe_mask, "label"], check_names=False)
