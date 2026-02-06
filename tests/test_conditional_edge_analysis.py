from __future__ import annotations

import numpy as np
import pandas as pd

from edge_discovery import conditional_edge


def test_conditional_edge_analysis_report_structure(monkeypatch) -> None:
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

    def fake_shap(model, x_train, x_test):
        vals = np.linspace(1.0, 0.2, x_test.shape[1])
        return pd.Series(vals, index=x_test.columns)

    monkeypatch.setattr(conditional_edge, "_mean_abs_shap_values", fake_shap)

    report = conditional_edge.run_conditional_edge_analysis(df, include_xgboost=False)

    assert report["decision"] in {"ACCEPT EDGE", "REJECT EDGE"}
    assert report["stability_report"]["folds"] >= 3
    assert not report["feature_importance_stability"].empty
    assert not report["per_year_performance"].empty
