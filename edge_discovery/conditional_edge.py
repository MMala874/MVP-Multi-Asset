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
        df.index = ts[ts.notna()]
    elif not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Dataset must provide timestamp column or DatetimeIndex")
    df = df.sort_index()
    return df


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
        tr = np.where((years >= test_start - train_years) & (years < test_start))[0]
        te = np.where((years >= test_start) & (years < test_start + test_years))[0]
        if len(tr) == 0 or len(te) == 0:
            continue
        left = max(0, te.min() - purge_bars)
        right = min(len(index) - 1, te.max() + purge_bars)
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
            out[m] = LogisticRegression(max_iter=2000, solver="lbfgs", random_state=42)
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
        vals = np.asarray(model.feature_importances_, dtype=float)
        return pd.Series(vals, index=cols)
    if hasattr(model, "coef_"):
        vals = np.abs(np.asarray(model.coef_[0], dtype=float))
        return pd.Series(vals, index=cols)
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
    df = _parse_dataset(dataset)
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and c != "label"]
    X_all = df[numeric_cols].replace([np.inf, -np.inf], np.nan)
    y_all = pd.to_numeric(df["label"], errors="coerce")
    valid = y_all.isin([0, 1])
    X_all, y_all = X_all.loc[valid], y_all.loc[valid].astype(int)

    if X_all.isna().any().any():
        X_all = X_all.fillna(X_all.median(numeric_only=True))

    years = X_all.index.year
    max_year = int(years.max())
    holdout_mask = years >= (max_year - holdout_years + 1)
    X_dev, y_dev = X_all.loc[~holdout_mask], y_all.loc[~holdout_mask]
    X_hold, y_hold = X_all.loc[holdout_mask], y_all.loc[holdout_mask]

    folds = _make_folds(X_dev.index, rolling_train_years, rolling_test_years, purge_bars)
    if not folds:
        raise ValueError("No valid folds produced.")

    models = [m.strip().lower() for m in (models or ["logreg", "gb", "xgb"]) if m.strip()]
    model_objs = _build_models(models, n_jobs=n_jobs, no_xgboost=no_xgboost)

    def eval_fold(model_name: str, fold: FoldData) -> dict[str, Any]:
        Xtr, ytr = X_dev.iloc[fold.train_idx], y_dev.iloc[fold.train_idx]
        Xte, yte = X_dev.iloc[fold.test_idx], y_dev.iloc[fold.test_idx]
        kept = _drop_corr(Xtr, 0.85)
        Xtr, Xte = Xtr[kept], Xte[kept]
        model = model_objs[model_name]
        model.fit(Xtr, ytr)
        p_tr = model.predict_proba(Xtr)[:, 1]
        p_te = model.predict_proba(Xte)[:, 1]

        def split_metrics(y: pd.Series, p: np.ndarray) -> dict[str, float]:
            thr = float(np.quantile(p, 1 - coverage)) if len(p) else 1.0
            sel = p >= thr
            base = float(y.mean())
            reg = float(y[sel].mean()) if sel.any() else float("nan")
            lift = reg - base if np.isfinite(reg) else float("nan")
            auc = float(roc_auc_score(y, p)) if y.nunique() > 1 else float("nan")
            pval = _one_sided_two_prop_p(int(y[sel].sum()), int(sel.sum()), int(y[~sel].sum()), int((~sel).sum())) if sel.any() and (~sel).any() else float("nan")
            return {"auc": auc, "lift": lift, "pval": pval}

        imp = _importance(model, kept).sort_values(ascending=False).head(10).index.tolist()
        return {
            "model": model_name,
            "year": fold.test_year,
            "train": split_metrics(ytr, p_tr),
            "val": split_metrics(yte, p_te),
            "top_features": imp,
        }

    fold_results = Parallel(n_jobs=n_jobs)(
        delayed(eval_fold)(m, f)
        for m in model_objs
        for f in folds
    )

    by_model: dict[str, list[dict[str, Any]]] = {}
    for r in fold_results:
        by_model.setdefault(r["model"], []).append(r)
    best_model = max(by_model, key=lambda m: np.nanmean([x["val"]["auc"] for x in by_model[m]]))

    X_dev_sel = X_dev[_drop_corr(X_dev, 0.85)]
    X_hold_sel = X_hold[X_dev_sel.columns]
    final_model = _build_models([best_model], n_jobs=n_jobs, no_xgboost=no_xgboost)[best_model]
    final_model.fit(X_dev_sel, y_dev)
    p_hold = final_model.predict_proba(X_hold_sel)[:, 1]
    thr_h = float(np.quantile(p_hold, 1 - coverage)) if len(p_hold) else 1.0
    sel_h = p_hold >= thr_h
    hold_auc = float(roc_auc_score(y_hold, p_hold)) if y_hold.nunique() > 1 else float("nan")
    hold_base = float(y_hold.mean())
    hold_region = float(y_hold[sel_h].mean()) if sel_h.any() else float("nan")
    hold_lift = hold_region - hold_base if np.isfinite(hold_region) else float("nan")
    hold_p = _one_sided_two_prop_p(int(y_hold[sel_h].sum()), int(sel_h.sum()), int(y_hold[~sel_h].sum()), int((~sel_h).sum())) if sel_h.any() and (~sel_h).any() else float("nan")

    best_folds = by_model[best_model]
    per_year_lift = {str(r["year"]): r["val"]["lift"] for r in best_folds}
    raw_pvals = [r["val"]["pval"] for r in best_folds] + [hold_p]
    adj_pvals = _bh_fdr(raw_pvals)
    hold_p_adj = adj_pvals[-1]

    # stability
    counts: dict[str, int] = {}
    for r in best_folds:
        for f in r["top_features"]:
            counts[f] = counts.get(f, 0) + 1
    stable = [f for f, c in counts.items() if c / len(best_folds) >= 0.6]

    year_lifts = np.array([v for v in per_year_lift.values() if np.isfinite(v)], dtype=float)
    dominance = (float(year_lifts.max()) / float(year_lifts.sum())) if len(year_lifts) and year_lifts.sum() > 0 else 1.0
    instability_high = len(stable) < 3

    if (hold_auc <= target_threshold) or (hold_lift <= 0.03) or instability_high:
        decision = "REJECT_EDGE"
        reason = "Failed holdout gate or instability gate"
    elif (not np.isfinite(hold_p_adj)) or (hold_p_adj > 0.05) or (dominance > 0.7):
        decision = "REJECT_EDGE"
        reason = "Failed significance/FDR or per-year dominance gate"
    else:
        decision = "ACCEPT_EDGE"
        reason = "Holdout and stability gates passed"

    return {
        "decision": decision,
        "reason": reason,
        "metrics": {
            "train_auc": float(np.nanmean([x["train"]["auc"] for x in best_folds])),
            "val_auc": float(np.nanmean([x["val"]["auc"] for x in best_folds])),
            "holdout_auc": hold_auc,
            "train_lift": float(np.nanmean([x["train"]["lift"] for x in best_folds])),
            "val_lift": float(np.nanmean([x["val"]["lift"] for x in best_folds])),
            "holdout_lift": hold_lift,
            "coverage": coverage,
            "p_values": {
                "raw": {**{f"val_{i}": p for i, p in enumerate(raw_pvals[:-1], start=1)}, "holdout": hold_p},
                "adjusted": {**{f"val_{i}": p for i, p in enumerate(adj_pvals[:-1], start=1)}, "holdout": hold_p_adj},
            },
            "per_year_lift": per_year_lift,
        },
        "stability_report": {
            "folds": len(best_folds),
            "final_stable_features": stable,
            "feature_importance_stability": [{"feature": k, "fold_freq": v / len(best_folds)} for k, v in sorted(counts.items(), key=lambda x: -x[1])],
        },
    }
