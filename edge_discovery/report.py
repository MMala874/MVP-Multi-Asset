from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def _stable_sign_last_5(yearly: list[dict]) -> tuple[int, int]:
    valid = [y for y in yearly if y["pass"]]
    last5 = sorted(valid, key=lambda x: x["year"])[-5:]
    if not last5:
        return (0, 0)
    signs = [y["sign"] for y in last5 if y["sign"] != 0]
    if not signs:
        return (0, len(last5))
    majority = 1 if sum(signs) > 0 else -1
    stable = sum(1 for s in signs if s == majority)
    return (stable, len(last5))


def build_shift_report(results_df: pd.DataFrame, yearly_map: dict[tuple[str, str], list[dict]], out_path: str | Path) -> dict:
    report = {"events": {}, "final_decision": []}

    for _, row in results_df.iterrows():
        event = row["event"]
        metric = row["metric"]
        yearly = yearly_map.get((event, metric), [])
        stable_count, years_count = _stable_sign_last_5(yearly)

        accepted = bool(
            (row["pvalue_perm"] < 0.05)
            and (years_count > 0)
            and (stable_count >= 4)
            and (0.02 <= row["coverage"] <= 0.15)
        )

        report["events"].setdefault(event, {})[metric] = {
            "horizon": int(row["horizon"]),
            "effect_delta": float(row["effect_delta"]),
            "effect_ratio": float(row["effect_ratio"]),
            "pvalue_perm": float(row["pvalue_perm"]),
            "ci_low": float(row["ci_low"]),
            "ci_high": float(row["ci_high"]),
            "n_event": int(row["n_event"]),
            "n_base": int(row["n_base"]),
            "coverage": float(row["coverage"]),
            "yearly": yearly,
            "decision": "ACCEPT" if accepted else "REJECT",
        }

        report["final_decision"].append(
            {
                "event": event,
                "metric": metric,
                "decision": "ACCEPT" if accepted else "REJECT",
            }
        )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
