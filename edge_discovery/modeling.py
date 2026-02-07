from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline

from edge_discovery.cv import build_purged_walk_forward_splits

FORBIDDEN_PATTERNS = re.compile(r"(fwd|mfe|mae|resolution|outcome|future|next|tp|sl)", re.IGNORECASE)


def enforce_leakage_firewall(feature_columns: list[str]) -> dict[str, list[str]]:
    blocked = [c for c in feature_columns if FORBIDDEN_PATTERNS.search(c)]
    allowed = [c for c in feature_columns if c not in blocked]
    if blocked:
        raise ValueError(f"Leakage firewall triggered; forbidden columns found: {blocked}")
    return {"blocked": blocked, "allowed": allowed}


def _build_model(name: str) -> Any:
    if name == "hgb":
        return HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, random_state=42)
    if name == "logreg":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("clf", LogisticRegression(max_iter=2000, solver="lbfgs")),
        ])
    if name == "xgb":
        from xgboost import XGBClassifier

        return XGBClassifier(
            n_estimators=300,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            random_state=42,
            tree_method="hist",
        )
    raise ValueError(f"Unsupported model {name}")


def _lift_at_top(y: np.ndarray, p: np.ndarray, coverage: float = 0.04) -> float:
    if len(y) == 0:
        return float("nan")
    thr = float(np.quantile(p, 1 - coverage))
    sel = p >= thr
    if sel.sum() == 0:
        return float("nan")
    return float(y[sel].mean() - y.mean())


def run_ml_optional(dataset: pd.DataFrame, model_name: str = "hgb", horizon: int = 20, top_coverage: float = 0.04) -> dict:
    df = dataset.copy()
    idx = pd.to_datetime(df["timestamp"], utc=True, errors="coerce") if "timestamp" in df.columns else pd.to_datetime(df.index, utc=True, errors="coerce")
    df = df.loc[idx.notna()].copy()
    df.index = pd.DatetimeIndex(idx[idx.notna()], name="timestamp")

    y = pd.to_numeric(df["label"], errors="coerce")
    feat_cols = [c for c in df.columns if c not in {"timestamp", "label", "event_name"} and pd.api.types.is_numeric_dtype(df[c])]
    firewall = enforce_leakage_firewall(feat_cols)

    X = df[firewall["allowed"]].astype(float)
    valid = y.isin([0, 1]) & X.notna().all(axis=1)
    X = X.loc[valid]
    y = y.loc[valid].astype(int)

    split = build_purged_walk_forward_splits(
        X.index,
        train_years=3,
        val_years=1,
        holdout_last_years=2,
        purge_bars=horizon + 10,
        embargo_bars=horizon + 10,
    )

    model = _build_model(model_name)
    fold_metrics = []
    for fold in split["folds"]:
        Xtr, ytr = X.iloc[fold["train_idx"]], y.iloc[fold["train_idx"]]
        Xv, yv = X.iloc[fold["val_idx"]], y.iloc[fold["val_idx"]]
        model.fit(Xtr, ytr)
        ptr = model.predict_proba(Xtr)[:, 1]
        pv = model.predict_proba(Xv)[:, 1]
        fold_metrics.append(
            {
                "year": fold["val_start_year"],
                "auc_train": float(roc_auc_score(ytr, ptr)) if ytr.nunique() > 1 else float("nan"),
                "auc_val": float(roc_auc_score(yv, pv)) if yv.nunique() > 1 else float("nan"),
                "lift_top_val": _lift_at_top(yv.to_numpy(), pv, coverage=top_coverage),
            }
        )

    model.fit(X.iloc[split["dev_idx"]], y.iloc[split["dev_idx"]])
    ph = model.predict_proba(X.iloc[split["holdout_idx"]])[:, 1]
    yh = y.iloc[split["holdout_idx"]]
    return {
        "model": model_name,
        "fold_metrics": fold_metrics,
        "holdout": {
            "auc": float(roc_auc_score(yh, ph)) if yh.nunique() > 1 else float("nan"),
            "lift_top": _lift_at_top(yh.to_numpy(), ph, coverage=top_coverage),
        },
        "leakage_report": firewall,
    }
