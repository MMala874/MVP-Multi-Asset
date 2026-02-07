from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import erf, sqrt
from typing import Any

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
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
    source_col: str | None = None
    timestamp_candidates = ["timestamp", "time", "datetime", "Date", "Time", "Unnamed: 0"]

    for col in timestamp_candidates:
        if col in out.columns:
            source_col = col
            break

    if source_col is None and len(out.columns) > 0:
        first_col = out.columns[0]
        first_values = out[first_col]
        parsed_first = pd.to_datetime(first_values, utc=True, errors="coerce")
        if not parsed_first.isna().all():
            source_col = str(first_col)

    if source_col is None:
        raise ValueError(
            "Dataset must have DatetimeIndex OR a parseable timestamp-like column "
            f"(checked: {timestamp_candidates}); available columns={list(out.columns)}"
        )

    parsed = pd.to_datetime(out[source_col], utc=True, errors="coerce")
    if parsed.isna().all():
        sample_values = out[source_col].head(3).tolist()
        raise ValueError(
            "Timestamp parsing failed: selected column "
            f"'{source_col}' produced all NaT. Available columns={list(out.columns)}; "
            f"first_3_values={sample_values}"
        )

    out["timestamp"] = parsed
    out = out.set_index("timestamp").sort_index()
    return out


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


def _feature_columns(dataset: pd.DataFrame, target_col: str) -> list[str]:
    timestamp_cols = {"timestamp", "time", "datetime", "date", "Date", "Time", "Unnamed: 0"}
    excluded = {
        target_col,
        "label",
        "bars_to_resolution",
        "outcome_type",
    }
    return [
        c
        for c in dataset.columns
        if c not in excluded
        and c not in timestamp_cols
        and not str(c).startswith("fwd_")
        and pd.api.types.is_numeric_dtype(dataset[c])
    ]


def _build_models(models: list[str], n_jobs: int) -> dict[str, Any]:
    selected = {m.strip().lower() for m in models if m.strip()}
    if not selected:
        raise ValueError("At least one model must be selected")

    unknown = selected.difference({"xgb", "logreg"})
    if unknown:
        raise ValueError(f"Unknown model(s): {', '.join(sorted(unknown))}")

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
            n_estimators=600,
            learning_rate=0.04,
            max_depth=3,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=1.0,
            min_child_weight=1,
            tree_method="hist",
            n_jobs=n_jobs,
            random_state=42,
            eval_metric="logloss",
        )

    return built


def _prepare_target(data: pd.DataFrame, target_col: str, target_mode: str, target_threshold: float) -> pd.Series:
    if target_col not in data.columns:
        raise ValueError(f"Dataset must contain target column '{target_col}'")

    src = data[target_col]
    if target_mode == "identity":
        y = pd.to_numeric(src, errors="coerce")
        non_binary = set(y.dropna().unique().tolist()).difference({0, 1})
        if non_binary:
            raise ValueError(f"target_mode='identity' requires 0/1 values in '{target_col}'")
        if y.isna().any():
            raise ValueError(f"target_mode='identity' found NaN/non-numeric values in '{target_col}'")
        return y.astype(int)

    src_num = pd.to_numeric(src, errors="coerce")
    if src_num.isna().all():
        raise ValueError(f"target column '{target_col}' has no numeric values for mode '{target_mode}'")

    if target_mode == "binary_gt0":
        return (src_num > 0).astype(int)
    if target_mode == "binary_threshold":
        return (src_num > float(target_threshold)).astype(int)
    raise ValueError(f"Unknown target_mode: {target_mode}")


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


def _evaluate_fold_models(
    fold_id: int,
    test_year: int,
    model_names: list[str],
    model_n_jobs: int,
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    prob_threshold: float,
) -> tuple[list[FoldResult], list[pd.DataFrame]]:
    fold_rows: list[FoldResult] = []
    importance_frames: list[pd.DataFrame] = []

    model_map = _build_models(model_names, n_jobs=model_n_jobs)
    for model_name, model in model_map.items():
        fitted_model = model.__class__(**model.get_params())
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

        fold_rows.append(
            FoldResult(
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
        )

        importance = _feature_importance_gain(fitted_model, model_name, x_test.columns)
        if not importance.empty:
            importance_frame = importance.reset_index()
            importance_frame.columns = ["feature", "importance_gain"]
            importance_frame["fold_id"] = fold_id
            importance_frame["test_year"] = test_year
            importance_frame["model"] = model_name
            importance_frames.append(importance_frame)

    return fold_rows, importance_frames


def _two_proportion_one_sided_pvalue(success_a: int, n_a: int, success_b: int, n_b: int) -> float:
    if n_a <= 0 or n_b <= 0:
        return float("nan")
    p_a = success_a / n_a
    p_b = success_b / n_b
    pooled = (success_a + success_b) / (n_a + n_b)
    variance = pooled * (1.0 - pooled) * ((1.0 / n_a) + (1.0 / n_b))
    if variance <= 0.0:
        return float("nan")
    z_score = (p_a - p_b) / sqrt(variance)
    cdf = 0.5 * (1.0 + erf(z_score / sqrt(2.0)))
    return float(max(0.0, min(1.0, 1.0 - cdf)))


def _apply_rare_event_filter(
    full_data: pd.DataFrame,
    event_cols: list[str],
    calibration_mask: pd.Series,
) -> pd.DataFrame:
    if not event_cols:
        return full_data

    out = full_data.copy()
    cal = out.loc[calibration_mask, event_cols]

    for col in event_cols:
        source = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
        cal_col = pd.to_numeric(cal[col], errors="coerce").dropna()
        if cal_col.empty:
            out[col] = 0.0
            continue

        lower = float(cal_col.quantile(0.05))
        upper = float(cal_col.quantile(0.95))
        rare_mask = (source < lower) | (source > upper)
        out[col] = rare_mask.astype(np.float32)

    return out


def _compute_split_metrics(y_true: pd.Series, proba: np.ndarray, prob_threshold: float) -> dict[str, float | int]:
    baseline = float(y_true.mean())
    region_mask = np.asarray(proba > prob_threshold, dtype=bool)
    coverage = float(region_mask.mean())

    if region_mask.any():
        region_tp = float(y_true.iloc[region_mask].mean())
        lift = float(region_tp - baseline)
    else:
        region_tp = float("nan")
        lift = float("nan")

    try:
        auc = float(roc_auc_score(y_true, proba))
    except ValueError:
        auc = float("nan")

    in_region = int(region_mask.sum())
    out_region = int((~region_mask).sum())
    return {
        "auc": auc,
        "lift": lift,
        "coverage": coverage,
        "region_tp": region_tp,
        "baseline_tp": baseline,
        "in_region": in_region,
        "out_region": out_region,
        "in_region_success": int(y_true.iloc[region_mask].sum()) if in_region > 0 else 0,
        "out_region_success": int(y_true.iloc[~region_mask].sum()) if out_region > 0 else 0,
    }


def _benjamini_hochberg(p_values: dict[str, float], alpha: float = 0.05) -> tuple[dict[str, float], list[str]]:
    finite = [(k, v) for k, v in p_values.items() if np.isfinite(v)]
    if not finite:
        return {k: float("nan") for k in p_values}, []

    m = len(finite)
    sorted_vals = sorted(finite, key=lambda item: item[1])
    adjusted_sorted: list[tuple[str, float]] = []
    running_min = 1.0
    for rank in range(m, 0, -1):
        key, p_val = sorted_vals[rank - 1]
        adj = min(1.0, p_val * m / rank)
        running_min = min(running_min, adj)
        adjusted_sorted.append((key, running_min))
    adjusted_sorted.reverse()
    adjusted = {k: float("nan") for k in p_values}
    adjusted.update({k: v for k, v in adjusted_sorted})
    significant = [k for k, v in adjusted.items() if np.isfinite(v) and v <= alpha]
    return adjusted, sorted(significant)


def run_conditional_edge_analysis(
    dataset: pd.DataFrame,
    prob_threshold: float = 0.55,
    corr_threshold: float = 0.85,
    unstable_feature_min_fold_frac: float = 0.6,
    models: list[str] | None = None,
    n_jobs: int | None = None,
    target_col: str = "label",
    target_mode: str = "identity",
    target_threshold: float = 0.0,
) -> dict[str, Any]:
    if n_jobs in (None, 0):
        import os
        n_jobs = max(1, os.cpu_count() or 1)
    n_jobs = max(1, int(n_jobs))

    data = _resolve_timestamp_index(dataset)

    if target_col not in data.columns:
        raise ValueError(
            f"Dataset must include a '{target_col}' column (double-barrier label). "
            f"Available columns={list(data.columns)}"
        )

    feature_cols = _feature_columns(data, target_col=target_col)
    x_all = data[feature_cols].astype(np.float32)
    if x_all.empty:
        raise ValueError("Dataset has no usable numeric feature columns after preprocessing")

    if x_all.isna().any().any():
        x_all = x_all.fillna(x_all.median(numeric_only=True))

    y_all = _prepare_target(data, target_col=target_col, target_mode=target_mode, target_threshold=target_threshold)

    years = data.index.year
    train_mask = (years >= 2009) & (years <= 2018)
    val_mask = (years >= 2019) & (years <= 2021)
    holdout_mask = (years >= 2022) & (years <= 2025)

    if train_mask.sum() == 0 or val_mask.sum() == 0 or holdout_mask.sum() == 0:
        raise ValueError("Dataset must contain bars for TRAIN_DEV(2009-2018), VALIDATION(2019-2021) and HOLDOUT(2022-2025)")

    calibration_mask = train_mask | val_mask
    event_cols = [c for c in feature_cols if c.startswith("event_")]
    filtered_x = _apply_rare_event_filter(x_all, event_cols=event_cols, calibration_mask=calibration_mask)

    models_to_run = models if models is not None else ["xgb", "logreg"]
    model_name = models_to_run[0]
    fitted_model = _build_models([model_name], n_jobs=n_jobs)[model_name]

    x_train = filtered_x.loc[train_mask]
    y_train = y_all.loc[train_mask]
    x_val = filtered_x.loc[val_mask]
    y_val = y_all.loc[val_mask]
    x_holdout = filtered_x.loc[holdout_mask]
    y_holdout = y_all.loc[holdout_mask]

    fitted_model.fit(x_train, y_train)

    train_proba = fitted_model.predict_proba(x_train)[:, 1]
    val_proba = fitted_model.predict_proba(x_val)[:, 1]
    holdout_proba = fitted_model.predict_proba(x_holdout)[:, 1]

    train_metrics = _compute_split_metrics(y_train, train_proba, prob_threshold=prob_threshold)
    validation_metrics = _compute_split_metrics(y_val, val_proba, prob_threshold=prob_threshold)
    holdout_metrics = _compute_split_metrics(y_holdout, holdout_proba, prob_threshold=prob_threshold)

    raw_p_values = {
        "train_lift": _two_proportion_one_sided_pvalue(
            success_a=train_metrics["in_region_success"],
            n_a=train_metrics["in_region"],
            success_b=train_metrics["out_region_success"],
            n_b=train_metrics["out_region"],
        ),
        "validation_lift": _two_proportion_one_sided_pvalue(
            success_a=validation_metrics["in_region_success"],
            n_a=validation_metrics["in_region"],
            success_b=validation_metrics["out_region_success"],
            n_b=validation_metrics["out_region"],
        ),
        "holdout_lift": _two_proportion_one_sided_pvalue(
            success_a=holdout_metrics["in_region_success"],
            n_a=holdout_metrics["in_region"],
            success_b=holdout_metrics["out_region_success"],
            n_b=holdout_metrics["out_region"],
        ),
    }
    adjusted_p_values, significant_after_fdr = _benjamini_hochberg(raw_p_values, alpha=0.05)

    holdout_df = pd.DataFrame(
        {
            "year": y_holdout.index.year,
            "y": y_holdout.to_numpy(),
            "proba": holdout_proba,
        }
    )
    holdout_df["region"] = holdout_df["proba"] > prob_threshold

    per_year_lift: dict[str, float] = {}
    strong_negative_years: list[str] = []
    for year in [2022, 2023, 2024, 2025]:
        year_data = holdout_df.loc[holdout_df["year"] == year]
        if year_data.empty:
            per_year_lift[str(year)] = float("nan")
            continue
        baseline = float(year_data["y"].mean())
        region = year_data.loc[year_data["region"], "y"]
        if region.empty:
            per_year_lift[str(year)] = float("nan")
            continue
        year_lift = float(region.mean() - baseline)
        per_year_lift[str(year)] = year_lift
        if year_lift < -0.05:
            strong_negative_years.append(str(year))

    sign_values = [np.sign(v) for v in per_year_lift.values() if np.isfinite(v) and v != 0.0]
    sign_flip_instability = bool(sign_values and (min(sign_values) < 0 < max(sign_values)))

    metrics = {
        "train_auc": train_metrics["auc"],
        "validation_auc": validation_metrics["auc"],
        "holdout_auc": holdout_metrics["auc"],
        "train_lift": train_metrics["lift"],
        "validation_lift": validation_metrics["lift"],
        "holdout_lift": holdout_metrics["lift"],
        "coverage": holdout_metrics["coverage"],
        "raw_p_values": raw_p_values,
        "adjusted_p_values": adjusted_p_values,
        "significant_after_fdr": significant_after_fdr,
        "per_year_lift": per_year_lift,
    }

    accept = (
        np.isfinite(metrics["holdout_auc"])
        and metrics["holdout_auc"] > 0.55
        and np.isfinite(metrics["holdout_lift"])
        and metrics["holdout_lift"] > 0.05
        and np.isfinite(metrics["coverage"])
        and metrics["coverage"] > 0.03
        and len(significant_after_fdr) > 0
        and not strong_negative_years
        and not sign_flip_instability
    )

    reason_parts: list[str] = []
    if not (np.isfinite(metrics["holdout_auc"]) and metrics["holdout_auc"] > 0.55):
        reason_parts.append("holdout_auc<=0.55")
    if not (np.isfinite(metrics["holdout_lift"]) and metrics["holdout_lift"] > 0.05):
        reason_parts.append("holdout_lift<=0.05")
    if not (np.isfinite(metrics["coverage"]) and metrics["coverage"] > 0.03):
        reason_parts.append("coverage<=3%")
    if len(significant_after_fdr) == 0:
        reason_parts.append("no_metric_significant_after_fdr")
    if strong_negative_years:
        reason_parts.append(f"strong_negative_years={','.join(strong_negative_years)}")
    if sign_flip_instability:
        reason_parts.append("holdout_lift_sign_flip")

    return {
        "decision": "ACCEPT_EDGE" if accept else "REJECT_EDGE",
        "reason": "all_strict_conditions_passed" if accept else "; ".join(reason_parts),
        "metrics": metrics,
    }
