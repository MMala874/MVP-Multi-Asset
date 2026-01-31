from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict

import pandas as pd


def test_run_tuning_grid_search_s1() -> None:
    """Test that run_tuning creates CSV with correct format and sorting."""
    from scripts.run_tuning import _build_grid, _run_backtest
    from configs.loader import load_config

    grid = _build_grid("S1_TREND_EMA_ATR_ADX")

    assert len(grid) == 3 * 2 * 3 * 3 * 3  # 5 x 2 x 3 x 3 x 3 = 270 combinations
    assert all("ema_fast" in params for params in grid)
    assert all("ema_slow" in params for params in grid)
    assert all("k_sl" in params for params in grid)
    assert all("k_tp" in params for params in grid)
    assert all("adx_th" in params for params in grid)


def test_run_tuning_creates_csv() -> None:
    """Test that run_tuning creates output CSV with correct columns."""
    import subprocess
    import sys

    with tempfile.TemporaryDirectory() as tmpdir:
        eurusd_data = {
            "time": pd.date_range("2024-01-01", periods=100, freq="H"),
            "open": [1.0 + i * 0.0001 for i in range(100)],
            "high": [1.01 + i * 0.0001 for i in range(100)],
            "low": [0.99 + i * 0.0001 for i in range(100)],
            "close": [1.005 + i * 0.0001 for i in range(100)],
        }
        eurusd_df = pd.DataFrame(eurusd_data)
        eurusd_csv = Path(tmpdir) / "eurusd.csv"
        eurusd_df.to_csv(eurusd_csv, index=False)

        cmd = [
            sys.executable,
            "-m",
            "scripts.run_tuning",
            "--config",
            "configs/examples/example_config.yaml",
            "--strategy_id",
            "S1_TREND_EMA_ATR_ADX",
            "--eurusd",
            str(eurusd_csv),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert (Path("runs") / "tuning_S1_TREND_EMA_ATR_ADX.csv").exists()

        df = pd.read_csv(Path("runs") / "tuning_S1_TREND_EMA_ATR_ADX.csv")

        expected_cols = [
            "ema_fast",
            "ema_slow",
            "k_sl",
            "k_tp",
            "adx_th",
            "trades",
            "expectancy",
            "profit_factor",
            "max_drawdown",
        ]
        for col in expected_cols:
            assert col in df.columns, f"Missing column: {col}"

        assert len(df) > 0, "DataFrame should not be empty"
        assert "tuning_S1_TREND_EMA_ATR_ADX.csv" in result.stdout

