from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from edge_discovery.econ_event_study import run_econ_event_study
from edge_discovery.event_study import run_event_study
from edge_discovery.modeling import run_ml_optional


def _bh_fdr(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = np.argsort(np.array(pvals, dtype=float))
    adj = np.full(m, np.nan)
    run = 1.0
    for rank in range(m, 0, -1):
        idx = order[rank - 1]
        p = pvals[idx]
        if not np.isfinite(p):
            continue
        run = min(run, min(1.0, p * m / rank))
        adj[idx] = run
    return adj.tolist()


def _diag_candidates(df: pd.DataFrame) -> list[str]:
    return sorted([c for c in df.columns if c.startswith("diag_r_mult_")])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", default="outputs/scan_report.json")
    ap.add_argument("--n_jobs", type=int, default=1)
    ap.add_argument("--top_k", type=int, default=10)
    ap.add_argument("--mode", choices=["classification", "econ"], default="econ")
    ap.add_argument("--ml_optional", action="store_true")
    args = ap.parse_args()
    _ = args.n_jobs

    df = pd.read_parquet(args.dataset) if args.dataset.endswith(".parquet") else pd.read_csv(args.dataset)
    events = sorted(df["event_name"].dropna().unique().tolist()) if "event_name" in df.columns else ["all"]

    rows = []
    if args.mode == "classification":
        coverages = [0.03, 0.04, 0.06]
        models = [None, "logreg", "hgb"]
        for ev in events:
            d = df[df["event_name"] == ev].copy() if ev != "all" and "event_name" in df.columns else df.copy()
            for cov in coverages:
                es = run_event_study(d, horizon=20, coverage=cov)
                p = es["holdout"]["pvalue"]
                for model in models:
                    ml = None
                    auc = np.nan
                    lift = es["holdout"]["lift"]
                    if model is not None:
                        ml = run_ml_optional(d, model_name=model, horizon=20, top_coverage=cov)
                        auc = ml["holdout"]["auc"]
                        lift = ml["holdout"]["lift_top"]
                    rows.append(
                        {
                            "event_name": ev,
                            "coverage": cov,
                            "model": model or "event_only",
                            "decision": es["decision"],
                            "holdout_pvalue": p,
                            "holdout_lift": lift,
                            "holdout_auc": auc,
                            "neg_year_ratio": es["stability"]["neg_year_ratio"],
                            "event_study": es,
                            "ml": ml,
                        }
                    )
        pvals = [float(r["holdout_pvalue"]) for r in rows]
        adj = _bh_fdr(pvals)
        for r, q in zip(rows, adj):
            r["holdout_pvalue_fdr"] = q
    else:
        for ev in events:
            d = df[df["event_name"] == ev].copy() if ev != "all" and "event_name" in df.columns else df.copy()
            for col in _diag_candidates(d):
                econ = run_econ_event_study(
                    d,
                    r_col=col,
                    horizon=20,
                    block_length=50,
                    holdout_gate_r=0.03,
                    max_neg_year_ratio=0.2,
                    stress_cost_r=0.5,
                )
                hold = econ["holdout"]
                row = {
                    "event_name": ev,
                    "hypothesis": col,
                    "E_train": hold["E_train"],
                    "E_holdout": hold["E_holdout"],
                    "CI_low": hold["CI_low"],
                    "CI_high": hold["CI_high"],
                    "pvalue": hold["pvalue"],
                    "neg_year_ratio": hold["neg_year_ratio"],
                    "decision": econ["decision"],
                    "econ_study": econ,
                }
                if args.ml_optional and econ["decision"] == "ACCEPT":
                    row["ml"] = run_ml_optional(d, model_name="hgb", horizon=20, top_coverage=0.04)
                else:
                    row["ml"] = None
                rows.append(row)

        pvals = [float(r["pvalue"]) for r in rows]
        adj = _bh_fdr(pvals)
        for r, q in zip(rows, adj):
            r["pvalue_fdr"] = q
            if np.isfinite(q) and q > 0.05 and r["decision"] == "ACCEPT":
                r["decision"] = "REJECT"

    results_df = pd.DataFrame([{k: v for k, v in r.items() if k not in {"event_study", "ml", "econ_study"}} for r in rows])
    out_dir = Path(args.out).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / "edge_scan_results.parquet"
    results_df.to_parquet(parquet_path, index=False)

    if args.mode == "econ":
        ranked = sorted(rows, key=lambda x: (x.get("pvalue_fdr", 1.0), -np.nan_to_num(x.get("E_holdout", np.nan), nan=-1e9)))[: args.top_k]
    else:
        ranked = sorted(rows, key=lambda x: (x["holdout_pvalue_fdr"], -x["holdout_lift"]))[: args.top_k]

    summary = {
        "mode": args.mode,
        "top_candidates": ranked,
        "n_hypotheses": len(rows),
        "results_parquet": str(parquet_path),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    with open(out_dir / "edge_scan_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"saved={args.out}")
    print(f"saved={parquet_path}")


if __name__ == "__main__":
    main()
