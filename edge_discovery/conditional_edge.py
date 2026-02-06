from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
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

    out = dataset.copy()
    for col in ("timestamp", "time"):
        if col not in out.columns:
            continue
        ts = pd.to_datetime(out[col], errors="coerce", utc=True)
        if ts.isna().any():
            continue
        out[col] = ts
        out = out.set_index(col).sort_index()
        return out

    raise ValueError("Dataset must have DatetimeIndex or parseable 'timestamp'/'time' column")


def _build_rolling_folds(index: pd.Index | np.ndarray, train_years: int = 3, test_years: int = 1, purge_bars: int = 10) -> list[tuple[np.ndarray, np.ndarray, int]]:
    if isinstance(index, pd.Index):
        years = pd.Index(index.year)
    else:
        years = pd.Index(pd.DatetimeIndex(index).year)

    unique_years = sorted(years.unique().tolist())
    folds: list[tuple[np.ndarray, np.ndarray, int]] = []

    for test_start in unique_years:
        train_start = test_start - train_years
        train_mask = np.asarray((years >= train_start) & (years < test_start), dtype=bool)
        test_mask = np.asarray((years >= test_start) & (years < test_start + test_years), dtype=bool)
        if train_mask.sum() == 0 or test_mask.sum() == 0:
            continue

        train_idx = np.flatnonzero(train_mask)
        test_idx = np.flatnonzero(test_mask)

        first_test = int(test_idx.min())
        last_test = int(test_idx.max())
        purge_left = max(first_test - purge_bars, 0)
        purge_right = min(last_test + purge_bars, len(years) - 1)

        keep_train = (train_idx < purge_left) | (train_idx > purge_right)
        purged_train_idx = train_idx[keep_train]
        if len(purged_train_idx) == 0:
            continue
        folds.append((purged_train_idx, test_idx, int(test_start)))

    return folds


def _feature_columns(dataset: pd.DataFrame) -> list[str]:
    excluded = {
        "label",
        "bars_to_resolution",
        "outcome_type",
        "timestamp",
        "time",
    }
    return [
        c
        for c in dataset.columns
        if c not in excluded and pd.api.types.is_numeric_dtype(dataset[c])
    ]


def _build_models(models: list[str], n_jobs: int) -> dict[str, Any]:
    selected = {m.strip().lower() for m in models if m.strip()}
    if not selected:
        raise ValueError("At least one model must be selected")

    built: dict[str, Any] = {}
    if "logreg" in selected:
        built["logreg"] = LogisticRegression(
            solver="saga",
            max_iter=2000,
            random_state=42,
        )

    if "xgb" in selected:
        try:
            from xgboost import XGBClassifier
        except ImportError as exc:
            raise ImportError("XGBoost selected but package 'xgboost' is not installed") from exc

        built["xgb"] = XGBClassifier(
            max_depth=3,
            n_estimators=300,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=42,
            tree_method="hist",
            nthread=n_jobs,
        )

    unknown = selected.difference({"xgb", "logreg"})
    if unknown:
        raise ValueError(f"Unknown model(s): {', '.join(sorted(unknown))}")

    return built


def _feature_importance_gain(model: Any, model_name: str, feature_names: pd.Index) -> pd.Series:
    if model_name != "xgb":
        return pd.Series(dtype=float)

    booster = model.get_booster()
    gains = booster.get_score(importance_type="gain")
    mapped_dict: dict[str, float] = {}
    for key, value in gains.items():
        if key in feature_names:
            mapped_dict[str(key)] = float(value)
            continue
        if key.startswith("f") and key[1:].isdigit():
            mapped_dict[str(feature_names[int(key[1:])])] = float(value)

    mapped = pd.Series(mapped_dict, dtype=float)
    if mapped.empty:
        return pd.Series(0.0, index=feature_names, dtype=float)
    return mapped.reindex(feature_names, fill_value=0.0).sort_values(ascending=False)


def _evaluate_fold_model(
    fold_id: int,
    test_year: int,
    model_name: str,
    model: Any,
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    prob_threshold: float,
) -> tuple[FoldResult, pd.DataFrame]:
    fitted_model = clone(model)
    fitted_model.fit(x_train, y_train)
    proba = fitted_model.predict_proba(x_test)[:, 1]

    baseline = float(y_test.mean())
    region_mask = proba > prob_threshold
    coverage = float(region_mask.mean())
    region_tp = float(y_test[region_mask].mean()) if region_mask.any() else np.nan
    lift_abs = float(region_tp - baseline) if not np.isnan(region_tp) else np.nan
    lift_ratio = float(region_tp / baseline) if (not np.isnan(region_tp) and baseline > 0) else np.nan

    try:
        auc = float(roc_auc_score(y_test, proba))
    except ValueError:
        auc = np.nan

    fold_result = FoldResult(
        fold_id=fold_id,
        test_year=test_year,
        model=model_name,
        n_train=len(x_train),
        n_test=len(x_test),
        baseline_tp_rate=baseline,
        region_coverage=coverage,
        region_tp_rate=region_tp,
        lift_abs=lift_abs,
        lift_ratio=lift_ratio,
        auc=auc,
    )

    importance = _feature_importance_gain(fitted_model, model_name, x_test.columns)
    importance_frame = importance.reset_index()
    importance_frame.columns = ["feature", "importance_gain"]
    importance_frame["fold_id"] = fold_id
    importance_frame["test_year"] = test_year
    importance_frame["model"] = model_name

    return fold_result, importance_frame


def run_conditional_edge_analysis(
    dataset: pd.DataFrame,
    prob_threshold: float = 0.55,
    corr_threshold: float = 0.85,
    unstable_feature_min_fold_frac: float = 0.6,
    n_jobs: int | None = None,
    models: list[str] | None = None,
) -> dict[str, Any]:
    if n_jobs in (None, 0):
        import os
        n_jobs = max(1, os.cpu_count() or 1)
    n_jobs = max(1, int(n_jobs))

    data = _resolve_timestamp_index(dataset)
    if "label" not in data.columns:
        raise ValueError("Dataset must contain a 'label' column")

    feature_cols = _feature_columns(data)
    x_all = data[feature_cols].astype(np.float32)
    if x_all.empty:
        raise ValueError("Dataset has no usable numeric feature columns after preprocessing")

    if x_all.isna().any().any():
        x_all = x_all.fillna(x_all.median(numeric_only=True))

    y_all = data["label"].astype(int)

    folds = _build_rolling_folds(data.index, train_years=3, test_years=1, purge_bars=10)
    if not folds:
        raise ValueError("No rolling 3y/1y folds available in the provided dataset")

    models_to_run = models if models is not None else ["xgb", "logreg"]
    model_map = _build_models(models_to_run, n_jobs=n_jobs)

    fold_rows: list[FoldResult] = []
    importance_frames: list[pd.DataFrame] = []

    for fold_id, (train_idx, test_idx, test_year) in enumerate(folds, start=1):
        x_train, x_test = x_all.iloc[train_idx], x_all.iloc[test_idx]
        y_train, y_test = y_all.iloc[train_idx], y_all.iloc[test_idx]
        for model_name, model in model_map.items():
            fold_result, importance_frame = _evaluate_fold_model(
                fold_id, test_year, model_name, model, x_train, x_test, y_train, y_test, prob_threshold
            )
            fold_rows.append(fold_result)
            if not importance_frame.empty:
                importance_frames.append(importance_frame)

    performance = pd.DataFrame([r.__dict__ for r in fold_rows]).sort_values(["fold_id", "model"])

    if importance_frames:
        importance_all = pd.concat(importance_frames, ignore_index=True)
    else:
        importance_all = pd.DataFrame(columns=["feature", "importance_gain", "fold_id", "test_year", "model"])

    xgb_importance = importance_all.loc[importance_all["model"] == "xgb"].copy()
    xgb_top10 = (
        xgb_importance.sort_values(["fold_id", "importance_gain"], ascending=[True, False])
        .groupby("fold_id", as_index=False)
        .head(10)
    ) if not xgb_importance.empty else pd.DataFrame(columns=xgb_importance.columns.tolist())

    fold_count = performance["fold_id"].nunique()
    xgb_stability = (
        xgb_top10.assign(in_top10=1)
        .groupby("feature", as_index=False)["in_top10"]
        .sum()
        .rename(columns={"in_top10": "top10_hits"})
    ) if not xgb_top10.empty else pd.DataFrame(columns=["feature", "top10_hits"])
    if not xgb_stability.empty:
        xgb_stability["stability_score"] = xgb_stability["top10_hits"] / float(fold_count)

    stable_features = xgb_stability.loc[
        xgb_stability["stability_score"] >= unstable_feature_min_fold_frac,
        "feature",
    ].tolist() if not xgb_stability.empty else []

    corr = x_all[stable_features].corr().abs() if stable_features else pd.DataFrame()
    dropped_corr: list[str] = []
    if not corr.empty and not xgb_importance.empty:
        importance_rank = xgb_importance.groupby("feature", as_index=False)["importance_gain"].mean().set_index("feature")
        for i, col_a in enumerate(corr.columns):
            for col_b in corr.columns[i + 1 :]:
                if corr.loc[col_a, col_b] > corr_threshold:
                    imp_a = float(importance_rank.loc[col_a, "importance_gain"])
                    imp_b = float(importance_rank.loc[col_b, "importance_gain"])
                    dropped_corr.append(col_a if imp_a < imp_b else col_b)

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
        "feature_importance_stability": xgb_stability.sort_values(["stability_score", "top10_hits"], ascending=[False, False])
        if not xgb_stability.empty else xgb_stability,
        "per_year_performance": perf_year.sort_values(["test_year", "model"]),
        "top_stable_feature_interactions": interactions.head(15),
        "regions_consistent_ptp_gt_055": interactions.loc[interactions["tp_rate_min_year"] > 0.55].head(15),
        "event_types_persistent_skew": event_skew.loc[event_skew["persistent_skew"]],
        "fold_performance": performance,
        "xgb_top_features_by_fold": xgb_top10.sort_values(["fold_id", "importance_gain"], ascending=[True, False]),
    }
