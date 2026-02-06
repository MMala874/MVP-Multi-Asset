from __future__ import annotations

import numpy as np
import pandas as pd

from edge_discovery.dataset_builder import build_shift_dataset


def test_build_shift_dataset_add_label_has_binary_values() -> None:
    rng = np.random.default_rng(123)
    n = 5000
    idx = pd.date_range("2021-01-01", periods=n, freq="15min")

    close = 1.10 + np.cumsum(rng.normal(0.0, 0.00045, n))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    spread = rng.uniform(0.00005, 0.00060, n)

    df = pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread,
            "close": close,
            "volume": rng.integers(50, 600, n),
        },
        index=idx,
    )

    out = build_shift_dataset(df, add_label=True)

    assert "label" in out.columns
    assert not out.empty
    assert set(out["label"].unique()).issubset({0, 1})
