from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def write_research_report(
    output_dir: str | Path,
    walkforward_folds: list[dict[str, Any]],
    stress_results: pd.DataFrame,
    bootstrap_summary: dict[str, Any],
) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(walkforward_folds).to_json(out / "walkforward_folds.json", orient="records", date_format="iso")
    stress_results.to_csv(out / "stress_results.csv", index=False)

    with (out / "bootstrap_ci.json").open("w", encoding="utf-8") as f:
        json.dump(bootstrap_summary, f, indent=2)
