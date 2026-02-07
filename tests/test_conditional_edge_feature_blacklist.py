from __future__ import annotations

import numpy as np
import pandas as pd

from edge_discovery.conditional_edge import run_conditional_edge_analysis


BLACKLISTED_EXACT = {"bars_to_resolution", "outcome_type"}


def _is_blacklisted(col: str) -> bool:
    col_l = col.lower()
    return col.startswith("fwd_") or ("mfe" in col_l) or ("mae" in col_l) or (col in BLACKLISTED_EXACT)


def test_conditional_edge_excludes_label_derived_leakage_features() -> None:
    idx = pd.date_range("2016-01-01", "2023-12-31", freq="D", tz="UTC")
    n = len(idx)
    rng = np.random.default_rng(123)

    df = pd.DataFrame(index=idx)
    df["feature_signal"] = rng.normal(0, 1, n)
    df["feature_noise"] = rng.normal(0, 1, n)

    # Intentionally strong, label-derived leakage columns that must be excluded.
    df["fwd_ret_10"] = rng.normal(0, 1, n)
    df["mfe_10_atr"] = rng.normal(0, 1, n)
    df["mae_10_atr"] = rng.normal(0, 1, n)
    df["bars_to_resolution"] = rng.integers(1, 10, n)
    df["outcome_type"] = np.where(rng.random(n) > 0.5, "TP", "SL")

    logits = 0.7 * df["feature_signal"] - 0.2 * df["feature_noise"]
    probs = 1.0 / (1.0 + np.exp(-logits))
    df["label"] = (rng.random(n) < probs).astype(int)

    report = run_conditional_edge_analysis(df, models=["logreg"], n_jobs=1)
    feature_cols = report["feature_cols"]

    assert "fwd_ret_10" not in feature_cols
    assert "mfe_10_atr" not in feature_cols
    assert "mae_10_atr" not in feature_cols
    assert "bars_to_resolution" not in feature_cols
    assert "outcome_type" not in feature_cols
    assert all(not _is_blacklisted(c) for c in feature_cols)
