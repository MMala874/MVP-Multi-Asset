from __future__ import annotations

import numpy as np
import pandas as pd

from edge_discovery.dataset_builder import build_research_dataset


def _make_m15_ohlcv(n: int = 3600, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=n, freq="15min")

    close = 1.08 + np.cumsum(rng.normal(0.0, 0.00035, n))
    open_ = np.roll(close, 1)
    open_[0] = close[0]

    spread = rng.uniform(0.00005, 0.00045, n)
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.integers(80, 500, n).astype(float)

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=index,
    )


def test_structural_edge_dataset_no_future_leakage() -> None:
    df = _make_m15_ohlcv()

    dataset_original = build_research_dataset(df)

    cutoff = 3000
    df_modified = df.copy()
    df_modified.iloc[cutoff + 1 :, df_modified.columns.get_loc("close")] += 0.015
    df_modified.iloc[cutoff + 1 :, df_modified.columns.get_loc("high")] += 0.015
    df_modified.iloc[cutoff + 1 :, df_modified.columns.get_loc("low")] += 0.015

    dataset_modified = build_research_dataset(df_modified)

    safe_time = df.index[cutoff - 11]

    cols_to_compare = [c for c in dataset_original.columns if c != "timestamp"]
    left = dataset_original.loc[dataset_original.index <= safe_time, cols_to_compare]
    right = dataset_modified.loc[dataset_modified.index <= safe_time, cols_to_compare]

    common_index = left.index.intersection(right.index)
    left = left.loc[common_index].sort_index()
    right = right.loc[common_index].sort_index()

    pd.testing.assert_frame_equal(left, right, check_dtype=False, check_exact=False, rtol=1e-10, atol=1e-12)
    assert not common_index.empty
