from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.data_pipeline.continuous_builder import build_continuous_contract
from src.data_pipeline.loader import download_minute
from src.data_pipeline.normalizer import save_parquet
from src.data_pipeline.quality import save_quality_report, validate_data


def test_build_continuous_contract_volume_roll() -> None:
    df = pd.DataFrame(
        {
            "timestamp": [
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:01:00Z",
                "2024-01-01T00:01:00Z",
            ],
            "open": [100, 101, 102, 103],
            "high": [101, 102, 103, 104],
            "low": [99, 100, 101, 102],
            "close": [100.5, 101.5, 102.5, 103.5],
            "volume": [1000, 2000, 3000, 100],
            "contract": ["ESH24", "ESM24", "ESH24", "ESM24"],
        }
    )

    out = build_continuous_contract(df, "volume")

    assert len(out) == 2
    assert out["active_contract"].tolist() == ["ESM24", "ESH24"]


def test_validate_data_missing_threshold() -> None:
    df = pd.DataFrame(
        {
            "timestamp": [
                "2024-01-01T00:00:00Z",
                "2024-01-01T00:01:00Z",
                "2024-01-01T00:03:00Z",
            ],
            "close": [1.0, 1.1, 1.2],
            "active_contract": ["ESH24", "ESH24", "ESM24"],
        }
    )

    report = validate_data(df)

    assert report["missing_minutes"] == 1
    assert report["expected_minutes"] == 4
    assert report["passes_missing_threshold"] is False
    assert report["rolls"] == 1


def test_download_and_save_with_local_files(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "futures_mvp" / "data"
    data_dir.mkdir(parents=True)
    sample = pd.DataFrame(
        {
            "timestamp": ["2024-01-01T00:00:00Z", "2024-01-01T00:01:00Z"],
            "open": [1.0, 1.1],
            "high": [1.0, 1.1],
            "low": [1.0, 1.1],
            "close": [1.0, 1.1],
            "volume": [10, 12],
            "contract": ["ESH24", "ESH24"],
        }
    )
    sample.to_csv(data_dir / "ES_1m.csv", index=False)

    monkeypatch.chdir(tmp_path)
    out = download_minute("ES", "2024-01-01", "2024-01-02")
    assert len(out) == 2

    parquet_path = tmp_path / "out" / "continuous.parquet"
    save_parquet(out, str(parquet_path))
    assert parquet_path.exists()

    report_path = tmp_path / "out" / "report.json"
    save_quality_report(validate_data(out), str(report_path))
    report = json.loads(report_path.read_text())
    assert "missing_ratio" in report
