from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from edge_discovery.forward_metrics import compute_forward_metrics


def test_forward_metrics_trailing_rows_nan_without_runtime_warnings() -> None:
    idx = pd.date_range("2021-01-01", periods=60, freq="H")
    close = pd.Series(np.linspace(100.0, 110.0, len(idx)), index=idx)
    df = pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5, "close": close})

    horizons = [5, 10, 20]
    max_h = max(horizons)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", category=RuntimeWarning)
        out = compute_forward_metrics(df, horizons=horizons)

    runtime_warnings = [w for w in caught if issubclass(w.category, RuntimeWarning)]
    assert runtime_warnings == []

    trailing = out.tail(max_h)
    for col in trailing.columns:
        assert trailing[col].isna().all()
