from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from edge_discovery import conditional_edge


def test_conditional_edge_analysis_report_structure() -> None:
    idx = pd.date_range("2016-01-01", "2023-12-31", freq="D")
    n = len(idx)
    rng = np.random.default_rng(42)

    df = pd.DataFrame(index=idx)
    df["event_breakout"] = (rng.random(n) > 0.7).astype(float)
    df["event_compression"] = (rng.random(n) > 0.75).astype(float)
    df["f_trend"] = np.sin(np.linspace(0, 20, n)) + rng.normal(0, 0.2, n)
    df["f_vol"] = rng.normal(0, 1, n)
    df["f_pos"] = rng.normal(0, 1, n)
    edge_score = 0.9 * df["event_breakout"] + 0.6 * (df["f_trend"] > 0).astype(float) - 0.2 * (df["f_vol"] > 1).astype(float)
    probs = 1.0 / (1.0 + np.exp(-(edge_score - 0.5)))
    df["label"] = (rng.random(n) < probs).astype(int)

    report = conditional_edge.run_conditional_edge_analysis(df, models=["logreg"])

    assert report["decision"] in {"ACCEPT EDGE", "REJECT EDGE"}
    assert report["stability_report"]["folds"] >= 3
    assert not report["per_year_performance"].empty
    assert report["feature_importance_stability"].empty


def test_conditional_edge_ignores_timestamp_string_column() -> None:
    pytest.importorskip("xgboost")
    idx = pd.date_range("2016-01-01", "2023-12-31", freq="D")
    n = len(idx)
    rng = np.random.default_rng(7)

    df = pd.DataFrame()
    df["timestamp"] = idx.astype(str)
    df["event_breakout"] = (rng.random(n) > 0.7).astype(float)
    df["feature_with_strings"] = np.where(rng.random(n) > 0.05, rng.normal(0, 1, n).round(4).astype(str), "bad")
    df["f_trend"] = np.sin(np.linspace(0, 15, n)) + rng.normal(0, 0.2, n)
    probs = 1.0 / (1.0 + np.exp(-(0.8 * df["event_breakout"] + 0.6 * (df["f_trend"] > 0).astype(float) - 0.5)))
    df["label"] = (rng.random(n) < probs).astype(int)

    report = conditional_edge.run_conditional_edge_analysis(df, models=["xgb"], n_jobs=2)

    features = set(report["xgb_top_features_by_fold"]["feature"].unique().tolist())
    assert "timestamp" not in features
    assert "feature_with_strings" not in features
    assert report["stability_report"]["folds"] >= 3


def test_conditional_edge_target_mode_binary_gt0() -> None:
    idx = pd.date_range("2016-01-01", "2023-12-31", freq="D")
    n = len(idx)
    rng = np.random.default_rng(99)

    df = pd.DataFrame(index=idx)
    df["event_breakout"] = (rng.random(n) > 0.75).astype(float)
    df["f_trend"] = rng.normal(0, 1, n)
    score = 0.9 * df["event_breakout"] + 0.5 * df["f_trend"] + rng.normal(0, 0.1, n)
    df["fwd_ret_mean_10"] = score

    report = conditional_edge.run_conditional_edge_analysis(
        df,
        models=["logreg"],
        target_col="fwd_ret_mean_10",
        target_mode="binary_gt0",
    )

    assert report["stability_report"]["folds"] >= 3
    assert not report["per_year_performance"].empty


def test_build_rolling_folds_accepts_numpy_datetime_array() -> None:
    idx = pd.date_range("2016-01-01", "2023-12-31", freq="D").to_numpy()
    folds = conditional_edge._build_rolling_folds(idx)
    assert len(folds) >= 3
