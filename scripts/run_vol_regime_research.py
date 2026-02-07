from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from edge_discovery.vol_regime_research import run_vol_regime_research


def _read_dataset(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    if not isinstance(df.index, pd.DatetimeIndex):
        ts_col = None
        for candidate in ("timestamp", "time", "datetime", "date", "Date", "Time"):
            if candidate in df.columns:
                ts_col = candidate
                break
        if ts_col is not None:
            df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
            df = df.set_index(ts_col)

    if isinstance(df.index, pd.DatetimeIndex):
        df = df.sort_index()
    return df


def _records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(8)
    return out.to_dict(orient="records")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run volatility compression-expansion regime research")
    parser.add_argument("--input", required=True, help="CSV/Parquet OHLC dataset path")
    parser.add_argument("--output", default="outputs/vol_regime_research_report.json", help="Output JSON path")
    args = parser.parse_args()

    dataset_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ohlc = _read_dataset(dataset_path)
    report = run_vol_regime_research(ohlc)

    payload = {
        "config": report["config"],
        "outcome_summary": _records(report["outcome_summary"]),
        "stats_summary": _records(report["stats_summary"]),
        "stability_per_year": _records(report["stability_per_year"]),
        "n_compression_events": int(report["event_flags"]["compression_start"].sum()),
        "n_expansion_up": int(report["event_flags"]["expansion_up"].sum()),
        "n_expansion_down": int(report["event_flags"]["expansion_down"].sum()),
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved research report to {output_path}")


if __name__ == "__main__":
    main()
