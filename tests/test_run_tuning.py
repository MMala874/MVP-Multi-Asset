from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Dict

import pandas as pd


def test_run_tuning_creates_output_files() -> None:
    """Test that run_tuning creates json and csv output files."""
    import subprocess
    import sys

    # Create a temporary directory for outputs
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create temporary CSV files with minimal data
        eurusd_data = {
            "time": pd.date_range("2024-01-01", periods=50, freq="H"),
            "open": [1.0 + i * 0.001 for i in range(50)],
            "high": [1.01 + i * 0.001 for i in range(50)],
            "low": [0.99 + i * 0.001 for i in range(50)],
            "close": [1.005 + i * 0.001 for i in range(50)],
        }
        eurusd_df = pd.DataFrame(eurusd_data)
        eurusd_csv = Path(tmpdir) / "eurusd.csv"
        eurusd_df.to_csv(eurusd_csv, index=False)

        out_dir = Path(tmpdir) / "results"

        # Run the tuning script
        cmd = [
            sys.executable,
            "scripts/run_tuning.py",
            "--config",
            "configs/examples/example_config.yaml",
            "--strategy_id",
            "S1_TREND_EMA_ATR_ADX",
            "--eurusd",
            str(eurusd_csv),
            "--out",
            str(out_dir),
            "--top_k",
            "3",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        # Check that the script ran successfully
        assert result.returncode == 0, f"Script failed with: {result.stderr}"

        # Check that output files were created
        assert (out_dir / "tuning_results.json").exists(), "tuning_results.json not created"
        assert (out_dir / "tuning_results.csv").exists(), "tuning_results.csv not created"
        assert (out_dir / "top_k.json").exists(), "top_k.json not created"
        assert (out_dir / "top_k.csv").exists(), "top_k.csv not created"

        # Validate JSON structure
        with open(out_dir / "tuning_results.json", "r") as f:
            all_results = json.load(f)
        assert isinstance(all_results, list), "tuning_results.json should be a list"

        with open(out_dir / "top_k.json", "r") as f:
            top_k_results = json.load(f)
        assert isinstance(top_k_results, list), "top_k.json should be a list"
        assert len(top_k_results) <= 3, "top_k should have at most 3 items"

        # Validate CSV structure
        all_csv = pd.read_csv(out_dir / "tuning_results.csv")
        assert "rank" in all_csv.columns, "CSV should have 'rank' column"
        assert "robust_score" in all_csv.columns, "CSV should have 'robust_score' column"

        top_k_csv = pd.read_csv(out_dir / "top_k.csv")
        assert "rank" in top_k_csv.columns, "top_k CSV should have 'rank' column"
        assert len(top_k_csv) <= 3, "top_k CSV should have at most 3 rows"

        # Validate that console output contains expected lines
        stdout = result.stdout
        assert "Candidates evaluated:" in stdout, "Missing 'Candidates evaluated:' in output"
        assert "Best robust_score:" in stdout, "Missing 'Best robust_score:' in output"
        assert "Outputs saved to:" in stdout, "Missing 'Outputs saved to:' in output"
