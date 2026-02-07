import json
from pathlib import Path

import numpy as np
import pandas as pd

from edge_discovery.conditional_edge import run_conditional_edge_analysis
from edge_discovery.dataset_builder import build_research_dataset


def _make_synthetic_ohlc(rows: int = 14000) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    idx = pd.date_range("2009-01-01", periods=rows, freq="12h", tz="UTC")
    noise = rng.normal(0, 0.0008, size=rows)
    close = 1.10 + np.cumsum(noise)
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0.0006, 0.0002, size=rows))
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = rng.integers(100, 1000, size=rows)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)


def main() -> None:
    out_dir = Path("outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    ohlc = _make_synthetic_ohlc()
    ds = build_research_dataset(ohlc, add_label=True)
    export_df = ds.reset_index(names="timestamp")
    csv_path = out_dir / "smoke_research_dataset.csv"
    export_df.to_csv(csv_path, index=False)

    loaded = pd.read_csv(csv_path)
    if "label" not in loaded.columns:
        raise AssertionError("Smoke test failure: 'label' column missing from saved dataset")
    ts = pd.to_datetime(loaded["timestamp"], utc=True, errors="coerce")
    if ts.isna().all():
        raise AssertionError("Smoke test failure: timestamp parsing produced all NaT")

    small = loaded.head(min(10000, len(loaded))).copy()
    report = run_conditional_edge_analysis(small, models=["xgb"], n_jobs=2, target_col="label")

    smoke_payload = {
        "decision": report["decision"],
        "reason": report["reason"],
        "metrics": report["metrics"],
    }

    out_path = out_dir / "smoke_report.json"
    out_path.write_text(json.dumps(smoke_payload, indent=2), encoding="utf-8")
    print(f"Saved smoke report: {out_path}")


if __name__ == "__main__":
    main()
