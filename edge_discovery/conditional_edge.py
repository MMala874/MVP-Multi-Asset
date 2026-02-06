from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score


@dataclass
class FoldResult:
    fold_id: int
    test_year: int
    model: str
    n_train: int
    n_test: int
    baseline_tp_rate: float
    region_coverage: float
    region_tp_rate: float
    lift_abs: float
    lift_ratio: float
    auc: float


def _resolve_timestamp_index(dataset: pd.DataFrame) -> pd.DataFrame:
    if isinstance(dataset.index, pd.DatetimeIndex):
        out = dataset.copy()
        out = out.sort_index()
        return out
    if "timestamp" not in dataset.columns:
        raise ValueError("Dataset must have DatetimeIndex or 'timestamp' column")
    out = dataset.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=False)
    out = out.set_index("timestamp").sort_index()
    return out


def _build_rolling_folds(index: pd.DatetimeIndex, train_years: int = 3, test_years: int = 1, purge_bars: int = 10) -> list[tuple[np.ndarray, np.ndarray, int]]:
    years = pd.Index(index.year)
    unique_years = sorted(years.unique())
    folds: list[tuple[np.ndarray, np.ndarray, int]] = []

    for test_start in unique_years:
        train_start = test_start - train_years
        train_mask = (years >= train_start) & (years < test_start)
        test_mask = (years >= test_start) & (years < test_start + test_years)
        if train_mask.sum() == 0 or test_mask.sum() == 0:
            continue

        train_idx = np.flatnonzero(train_mask.to_numpy())
        test_idx = np.flatnonzero(test_mask.to_numpy())

        first_test = int(test_idx.min())
        last_test = int(test_idx.max())
        purge_left = max(first_test - purge_bars, 0)
        purge_right = min(last_test + purge_bars, len(index) - 1)

        keep_train = (train_idx < purge_left) | (train_idx > purge_right)
        purged_train_idx = train_idx[keep_train]
        if len(purged_train_idx) == 0:
            continue
        folds.append((purged_train_idx, test_idx, test_start))

    return folds


def _feature_columns(dataset: pd.DataFrame) -> list[str]:
    excluded = {
        "label",
        "bars_to_resolution",
        "outcome_type",
        "timestamp",
        "time",
    }
    cols = [c for c in dataset.columns if c not in excluded]
    return cols


def _build_models(include_xgboost: bool = True) -> dict[str, Any]:
    models: dict[str, Any] = {
        "logistic_regression": LogisticRegression(max_iter=1000, random_state=42),
        "gradient_boosting_d3": GradientBoostingClassifier(max_depth=3, learning_rate=0.05, n_estimators=200, random_state=42),
    }

    if include_xgboost:
        try:
            from xgboost import XGBClassifier
        except ImportError as exc:
            raise ImportError("XGBoost requested but package 'xgboost' is not installed") from exc

        models["xgboost_d3"] = XGBClassifier(
            n_estimators=250,
            learning_rate=0.03,
            max_depth=3,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=42,
        )

    return models


def _mean_abs_shap_values(model: Any, x_train: pd.DataFrame, x_test: pd.DataFrame) -> pd.Series:
    try:
        import shap
    except ImportError as exc:
        raise ImportError("SHAP package is required for this analysis") from exc

    background_n = min(len(x_train), 200)
    eval_n = min(len(x_test), 500)
    background = x_train.sample(n=background_n, random_state=42)
    eval_x = x_test.iloc[:eval_n]

    explainer = shap.Explainer(model, background)
    shap_values = explainer(eval_x)
    vals = shap_values.values
    if vals.ndim == 3:
        vals = vals[:, :, 1]
    mean_abs = np.abs(vals).mean(axis=0)
    return pd.Series(mean_abs, index=x_test.columns)


def run_conditional_edge_analysis(
    dataset: pd.DataFrame,
    prob_threshold: float = 0.55,
    corr_threshold: float = 0.85,
    unstable_feature_min_fold_frac: float = 0.6,
    include_xgboost: bool = True,
) -> dict[str, Any]:
    data = _resolve_timestamp_index(dataset)
    if "label" not in data.columns:
        raise ValueError("Dataset must contain a 'label' column")

    feature_cols = _feature_columns(data)
    x_all = data[feature_cols].apply(pd.to_numeric, errors="coerce")
    x_all = x_all.dropna(axis=1, how="all")
    if x_all.empty:
        raise ValueError("Dataset has no usable numeric feature columns after preprocessing")

    if x_all.isna().any().any():
        x_all = x_all.fillna(x_all.median(numeric_only=True))

    y_all = data["label"].astype(int)

    folds = _build_rolling_folds(data.index, train_years=3, test_years=1, purge_bars=10)
    if not folds:
        raise ValueError("No rolling 3y/1y folds available in the provided dataset")

    models = _build_models(include_xgboost=include_xgboost)

    fold_rows: list[FoldResult] = []
    shap_rows: list[pd.DataFrame] = []

    for fold_id, (train_idx, test_idx, test_year) in enumerate(folds, start=1):
        x_train, x_test = x_all.iloc[train_idx], x_all.iloc[test_idx]
        y_train, y_test = y_all.iloc[train_idx], y_all.iloc[test_idx]

        for model_name, model in models.items():
            model.fit(x_train, y_train)
            proba = model.predict_proba(x_test)[:, 1]
            baseline = float(y_test.mean())
            region_mask = proba > prob_threshold
            coverage = float(region_mask.mean())
            if region_mask.any():
                region_tp = float(y_test[region_mask].mean())
            else:
                region_tp = np.nan
            lift_abs = float(region_tp - baseline) if not np.isnan(region_tp) else np.nan
            lift_ratio = float(region_tp / baseline) if (not np.isnan(region_tp) and baseline > 0) else np.nan

            try:
                auc = float(roc_auc_score(y_test, proba))
            except ValueError:
                auc = np.nan

            fold_rows.append(
                FoldResult(
                    fold_id=fold_id,
                    test_year=test_year,
                    model=model_name,
                    n_train=len(train_idx),
                    n_test=len(test_idx),
                    baseline_tp_rate=baseline,
                    region_coverage=coverage,
                    region_tp_rate=region_tp,
                    lift_abs=lift_abs,
                    lift_ratio=lift_ratio,
                    auc=auc,
                )
            )

            shap_importance = _mean_abs_shap_values(model, x_train, x_test)
            shap_frame = shap_importance.reset_index()
            shap_frame.columns = ["feature", "mean_abs_shap"]
            shap_frame["fold_id"] = fold_id
            shap_frame["test_year"] = test_year
            shap_frame["model"] = model_name
            shap_rows.append(shap_frame)

    performance = pd.DataFrame([r.__dict__ for r in fold_rows])
    shap_all = pd.concat(shap_rows, ignore_index=True)

    top10 = (
        shap_all.sort_values(["model", "fold_id", "mean_abs_shap"], ascending=[True, True, False])
        .groupby(["model", "fold_id"], as_index=False)
        .head(10)
    )
    top10["in_top10"] = 1

    fold_count = performance["fold_id"].nunique()
    stability = (
        top10.groupby(["model", "feature"], as_index=False)["in_top10"]
        .sum()
        .rename(columns={"in_top10": "top10_hits"})
    )
    stability["fold_fraction"] = stability["top10_hits"] / float(fold_count)

    shap_mean = shap_all.groupby(["model", "feature"], as_index=False)["mean_abs_shap"].mean()
    feature_stability = stability.merge(shap_mean, on=["model", "feature"], how="left")
    stable_features = feature_stability.loc[
        feature_stability["fold_fraction"] >= unstable_feature_min_fold_frac,
        "feature",
    ].unique().tolist()

    corr = x_all[stable_features].corr().abs() if stable_features else pd.DataFrame()
    dropped_corr: list[str] = []
    if not corr.empty:
        importance_rank = (
            feature_stability.groupby("feature", as_index=False)["mean_abs_shap"].mean().set_index("feature")
        )
        for i, col_a in enumerate(corr.columns):
            for col_b in corr.columns[i + 1 :]:
                if corr.loc[col_a, col_b] > corr_threshold:
                    imp_a = float(importance_rank.loc[col_a, "mean_abs_shap"])
                    imp_b = float(importance_rank.loc[col_b, "mean_abs_shap"])
                    drop_col = col_a if imp_a < imp_b else col_b
                    dropped_corr.append(drop_col)

    dropped_corr = sorted(set(dropped_corr))
    final_features = [f for f in stable_features if f not in dropped_corr]

    interaction_rows: list[dict[str, Any]] = []
    for f1, f2 in combinations(final_features[:15], 2):
        q1 = x_all[f1].quantile(0.7)
        q2 = x_all[f2].quantile(0.7)
        mask = (x_all[f1] >= q1) & (x_all[f2] >= q2)
        if mask.mean() < 0.03:
            continue

        per_year = data.loc[mask, "label"].groupby(data.loc[mask].index.year).mean()
        if len(per_year) < 2:
            continue
        if bool((per_year > prob_threshold).all()):
            interaction_rows.append(
                {
                    "feature_1": f1,
                    "feature_2": f2,
                    "support": float(mask.mean()),
                    "tp_rate_mean": float(per_year.mean()),
                    "tp_rate_min_year": float(per_year.min()),
                }
            )

    interactions = pd.DataFrame(interaction_rows).sort_values(
        ["tp_rate_min_year", "tp_rate_mean"], ascending=False
    ) if interaction_rows else pd.DataFrame(columns=["feature_1", "feature_2", "support", "tp_rate_mean", "tp_rate_min_year"])

    event_cols = [c for c in feature_cols if c.startswith("event_")]
    event_rows: list[dict[str, Any]] = []
    for e in event_cols:
        event_mask = x_all[e] > 0
        if event_mask.sum() < 30:
            continue
        per_year = y_all[event_mask].groupby(data.index.year[event_mask]).mean()
        if len(per_year) < 2:
            continue
        event_rows.append(
            {
                "event": e,
                "support": int(event_mask.sum()),
                "tp_rate_mean": float(per_year.mean()),
                "tp_rate_min_year": float(per_year.min()),
                "persistent_skew": bool((per_year > 0.5).all() or (per_year < 0.5).all()),
            }
        )

    event_skew = pd.DataFrame(event_rows).sort_values("tp_rate_mean", ascending=False) if event_rows else pd.DataFrame(
        columns=["event", "support", "tp_rate_mean", "tp_rate_min_year", "persistent_skew"]
    )

    perf_year = (
        performance.groupby(["test_year", "model"], as_index=False)[
            ["baseline_tp_rate", "region_tp_rate", "lift_abs", "lift_ratio", "auc", "region_coverage"]
        ].mean()
    )

    median_lift = performance["lift_abs"].median(skipna=True)
    stable_count = len(final_features)
    decision = "ACCEPT EDGE" if (median_lift >= 0.03 and stable_count >= 5 and not interactions.empty) else "REJECT EDGE"

    return {
        "decision": decision,
        "stability_report": {
            "folds": fold_count,
            "stable_features_before_corr_drop": len(stable_features),
            "dropped_for_high_correlation": dropped_corr,
            "final_stable_features": final_features,
        },
        "feature_importance_stability": feature_stability.sort_values(["model", "fold_fraction", "mean_abs_shap"], ascending=[True, False, False]),
        "per_year_performance": perf_year.sort_values(["test_year", "model"]),
        "top_stable_feature_interactions": interactions.head(15),
        "regions_consistent_ptp_gt_055": interactions.loc[interactions["tp_rate_min_year"] > 0.55].head(15),
        "event_types_persistent_skew": event_skew.loc[event_skew["persistent_skew"]],
        "fold_performance": performance,
    }
