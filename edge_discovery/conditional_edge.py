from __future__ import annotations

from dataclasses import dataclass
from math import erf, sqrt
from typing import Any

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score


@dataclass
class FoldData:
    train_idx: np.ndarray
    test_idx: np.ndarray
    test_year: int


def _parse_dataset(dataset: pd.DataFrame) -> pd.DataFrame:
    df = dataset.copy()
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df = df.loc[ts.notna()].copy()
        df.index = pd.DatetimeIndex(ts[ts.notna()], name="timestamp")
    elif isinstance(df.index, pd.DatetimeIndex):
        idx = pd.to_datetime(df.index, utc=True, errors="coerce")
        df = df.loc[idx.notna()].copy()
        df.index = pd.DatetimeIndex(idx[idx.notna()], name="timestamp")
    else:
        raise ValueError("Dataset must provide timestamp column or DatetimeIndex")
    return df.sort_index()


def _finite_assert(X: pd.DataFrame) -> None:
    bad = ~np.isfinite(X.to_numpy(dtype=float))
    if not bad.any():
        return
    counts = dict(zip(X.columns, bad.sum(axis=0).tolist()))
    bad_counts = {k: v for k, v in counts.items() if v > 0}
    raise ValueError(f"Non-finite values found in features: {bad_counts}")


def _bh_fdr(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = np.argsort(np.array(pvals, dtype=float))
    adj = np.full(m, np.nan)
    run = 1.0
    for rank in range(m, 0, -1):
        idx = order[rank - 1]
        v = pvals[idx]
        if not np.isfinite(v):
            continue
        run = min(run, min(1.0, v * m / rank))
        adj[idx] = run
    return adj.tolist()


def _one_sided_two_prop_p(success_a: int, n_a: int, success_b: int, n_b: int) -> float:
    if n_a <= 0 or n_b <= 0:
        return float("nan")
    p_a, p_b = success_a / n_a, success_b / n_b
    pooled = (success_a + success_b) / (n_a + n_b)
    var = pooled * (1 - pooled) * ((1 / n_a) + (1 / n_b))
    if var <= 0:
        return float("nan")
    z = (p_a - p_b) / sqrt(var)
    cdf = 0.5 * (1.0 + erf(z / sqrt(2.0)))
    return float(1.0 - cdf)


def _make_folds(index: pd.DatetimeIndex, train_years: int, test_years: int, purge_bars: int) -> list[FoldData]:
    years = pd.Index(index.year)
    uniq = sorted(years.unique())
    out: list[FoldData] = []
    for test_start in uniq:
        train_start = test_start - train_years
        tr = np.where((years >= train_start) & (years < test_start))[0]
        te = np.where((years >= test_start) & (years < test_start + test_years))[0]
        if len(tr) == 0 or len(te) == 0:
            continue
        left = max(0, int(te.min()) - purge_bars)
        right = min(len(index) - 1, int(te.max()) + purge_bars)
        tr = tr[(tr < left) | (tr > right)]
        if len(tr) == 0:
            continue
        out.append(FoldData(train_idx=tr, test_idx=te, test_year=int(test_start)))
    return out


def _drop_corr(X: pd.DataFrame, threshold: float) -> list[str]:
    corr = X.corr().abs()
    cols = list(corr.columns)
    remove: set[str] = set()
    for i, c in enumerate(cols):
        if c in remove:
            continue
        for j in range(i):
            c2 = cols[j]
            if c2 in remove:
                continue
            if corr.loc[c, c2] > threshold:
                remove.add(c)
                break
    return [c for c in cols if c not in remove]


def _build_models(models: list[str], n_jobs: int, no_xgboost: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for m in models:
        if m == "logreg":
            out[m] = LogisticRegression(max_iter=3000, solver="saga", random_state=42)
        elif m == "gb":
            out[m] = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, random_state=42)
        elif m == "xgb" and not no_xgboost:
            try:
                from xgboost import XGBClassifier
            except Exception:
                continue
            out[m] = XGBClassifier(
                n_estimators=300,
                max_depth=3,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                eval_metric="logloss",
                random_state=42,
                nthread=n_jobs,
                tree_method="hist",
            )
    return out


def _importance(model: Any, cols: list[str]) -> pd.Series:
    if hasattr(model, "feature_importances_"):
        return pd.Series(np.asarray(model.feature_importances_, dtype=float), index=cols)
    if hasattr(model, "coef_"):
        return pd.Series(np.abs(np.asarray(model.coef_[0], dtype=float)), index=cols)
    if hasattr(model, "get_booster"):
        score = model.get_booster().get_score(importance_type="gain")
        return pd.Series([score.get(f"f{i}", 0.0) for i in range(len(cols))], index=cols)
    return pd.Series(dtype=float)


def run_conditional_edge_analysis(
    dataset: pd.DataFrame,
    models: list[str] | None = None,
    n_jobs: int = 1,
    coverage: float = 0.04,
    target_threshold: float = 0.55,
    purge_bars: int = 10,
    rolling_train_years: int = 3,
    rolling_test_years: int = 1,
    holdout_years: int = 1,
    no_xgboost: bool = False,
) -> dict[str, Any]:
    del holdout_years
    df = _parse_dataset(dataset)

    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and c != "label"]
    X_all = df[numeric_cols].astype(float)
    y_all = pd.to_numeric(df["label"], errors="coerce")
    valid = y_all.isin([0, 1])
    X_all, y_all = X_all.loc[valid], y_all.loc[valid].astype(int)
    _finite_assert(X_all)

    years = X_all.index.year
    holdout_year = int(years.max())
    holdout_mask = years == holdout_year
    X_dev, y_dev = X_all.loc[~holdout_mask], y_all.loc[~holdout_mask]
    X_hold, y_hold = X_all.loc[holdout_mask], y_all.loc[holdout_mask]

    folds = _make_folds(X_dev.index, rolling_train_years, rolling_test_years, purge_bars)
    if not folds:
        raise ValueError("No valid validation folds produced with 3y/1y rolling split and purge.")

    model_names = [m.strip().lower() for m in (models or ["logreg", "gb", "xgb"]) if m.strip()]
    model_objs = _build_models(model_names, n_jobs=max(1, n_jobs), no_xgboost=no_xgboost)
    if not model_objs:
        raise ValueError("No usable models were initialized.")

    def split_metrics(y: pd.Series, p: np.ndarray) -> dict[str, float]:
        thr = float(np.quantile(p, 1 - coverage)) if len(p) else 1.0
        sel = p >= thr
        base = float(y.mean())
        reg = float(y[sel].mean()) if sel.any() else float("nan")
        lift = reg - base if np.isfinite(reg) else float("nan")
        auc = float(roc_auc_score(y, p)) if y.nunique() > 1 else float("nan")
        pval = _one_sided_two_prop_p(int(y[sel].sum()), int(sel.sum()), int(y[~sel].sum()), int((~sel).sum())) if sel.any() and (~sel).any() else float("nan")
        return {"auc": auc, "lift": lift, "pval": pval}

    def eval_fold(model_name: str, fold: FoldData) -> dict[str, Any]:
        Xtr, ytr = X_dev.iloc[fold.train_idx], y_dev.iloc[fold.train_idx]
        Xte, yte = X_dev.iloc[fold.test_idx], y_dev.iloc[fold.test_idx]
        kept = _drop_corr(Xtr, 0.85)
        Xtr, Xte = Xtr[kept], Xte[kept]
        model = _build_models([model_name], n_jobs=max(1, n_jobs), no_xgboost=no_xgboost)[model_name]
        model.fit(Xtr, ytr)
        p_tr = model.predict_proba(Xtr)[:, 1]
        p_te = model.predict_proba(Xte)[:, 1]
        imp = _importance(model, kept).sort_values(ascending=False).head(10).index.tolist()
        return {
            "model": model_name,
            "year": fold.test_year,
            "train": split_metrics(ytr, p_tr),
            "val": split_metrics(yte, p_te),
            "top_features": imp,
        }

    fold_results = Parallel(n_jobs=max(1, n_jobs))(delayed(eval_fold)(m, f) for m in model_objs for f in folds)

    by_model: dict[str, list[dict[str, Any]]] = {}
    for r in fold_results:
        by_model.setdefault(r["model"], []).append(r)

    best_model = max(by_model, key=lambda m: np.nanmean([x["val"]["auc"] for x in by_model[m]]))
    best_folds = sorted(by_model[best_model], key=lambda x: x["year"])

    kept_final = _drop_corr(X_dev, 0.85)
    X_dev_sel = X_dev[kept_final]
    X_hold_sel = X_hold[kept_final]
    final_model = _build_models([best_model], n_jobs=max(1, n_jobs), no_xgboost=no_xgboost)[best_model]
    final_model.fit(X_dev_sel, y_dev)

    p_hold = final_model.predict_proba(X_hold_sel)[:, 1]
    hold_metrics = split_metrics(y_hold, p_hold)

    per_year_lift = {str(r["year"]): r["val"]["lift"] for r in best_folds}
    year_lifts = np.array([v for v in per_year_lift.values() if np.isfinite(v)], dtype=float)
    neg_ratio = float((year_lifts < 0).mean()) if len(year_lifts) else 1.0

    raw_pvals = [r["val"]["pval"] for r in best_folds] + [hold_metrics["pval"]]
    adj_pvals = _bh_fdr(raw_pvals)

    counts: dict[str, int] = {}
    for r in best_folds:
        for f in r["top_features"]:
            counts[f] = counts.get(f, 0) + 1

    reasons: list[str] = []
    if hold_metrics["auc"] < max(0.55, target_threshold):
        reasons.append(f"holdout_auc {hold_metrics['auc']:.4f} < 0.55")
    if hold_metrics["lift"] < 0.08:
        reasons.append(f"holdout_lift {hold_metrics['lift']:.4f} < 0.08 at coverage={coverage}")
    if neg_ratio > 0.20:
        reasons.append(f"negative per-year in-sample lift ratio {neg_ratio:.2%} > 20%")

    decision = "ACCEPT_EDGE" if not reasons else "REJECT_EDGE"
    reason = "All gates passed" if not reasons else "; ".join(reasons)

    return {
        "decision": decision,
        "reason": reason,
        "selected_model": best_model,
        "metrics": {
            "train_auc": float(np.nanmean([x["train"]["auc"] for x in best_folds])),
            "val_auc": float(np.nanmean([x["val"]["auc"] for x in best_folds])),
            "holdout_auc": float(hold_metrics["auc"]),
            "train_lift": float(np.nanmean([x["train"]["lift"] for x in best_folds])),
            "val_lift": float(np.nanmean([x["val"]["lift"] for x in best_folds])),
            "holdout_lift": float(hold_metrics["lift"]),
            "coverage": coverage,
            "per_year_lift": per_year_lift,
            "neg_year_lift_ratio": neg_ratio,
            "p_values": {
                "raw": {**{f"val_{i}": p for i, p in enumerate(raw_pvals[:-1], start=1)}, "holdout": raw_pvals[-1]},
                "adjusted": {**{f"val_{i}": p for i, p in enumerate(adj_pvals[:-1], start=1)}, "holdout": adj_pvals[-1]},
            },
        },
        "stability_report": {
            "folds": len(best_folds),
            "feature_importance_stability": [
                {"feature": k, "fold_freq": v / len(best_folds)} for k, v in sorted(counts.items(), key=lambda x: -x[1])
            ],
        },
    }
