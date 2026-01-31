from __future__ import annotations

import pandas as pd
import tempfile
from pathlib import Path

from tuning.grid import build_grid
from tuning.worker import run_worker


def test_grid_s1_size() -> None:
    """Test that grid for S1 has correct size."""
    grid = build_grid("S1_TREND_EMA_ATR_ADX")
    expected_size = 3 * 2 * 4 * 4 * 3 * 2 * 2
    assert len(grid) == expected_size, f"Expected {expected_size}, got {len(grid)}"


def test_grid_s1_keys() -> None:
    """Test that all grid entries have required keys."""
    grid = build_grid("S1_TREND_EMA_ATR_ADX")
    required_keys = {
        "ema_fast",
        "ema_slow",
        "adx_th",
        "k_sl",
        "k_tp",
        "min_sl_points",
        "min_tp_points",
    }
    for params in grid:
        assert set(params.keys()) == required_keys


def test_worker_output_structure() -> None:
    """Test worker function output for one parameter set."""
    with tempfile.TemporaryDirectory() as tmpdir:
        eurusd_data = {
            "time": pd.date_range("2024-01-01", periods=100, freq="1h"),
            "open": [1.0 + i * 0.0001 for i in range(100)],
            "high": [1.01 + i * 0.0001 for i in range(100)],
            "low": [0.99 + i * 0.0001 for i in range(100)],
            "close": [1.005 + i * 0.0001 for i in range(100)],
        }
        eurusd_df = pd.DataFrame(eurusd_data)
        eurusd_csv = Path(tmpdir) / "eurusd.csv"
        eurusd_df.to_csv(eurusd_csv, index=False)

        params = {
            "ema_fast": 20,
            "ema_slow": 50,
            "adx_th": 20,
            "k_sl": 1.5,
            "k_tp": 1.0,
            "min_sl_points": 5.0,
            "min_tp_points": 5.0,
        }

        df_paths = {
            "EURUSD": str(eurusd_csv),
            "GBPUSD": None,
            "USDJPY": None,
        }

        result = run_worker(
            "configs/examples/example_config.yaml",
            "S1_TREND_EMA_ATR_ADX",
            params,
            df_paths,
        )

        expected_keys = {
            "params",
            "trades_A",
            "trades_B",
            "trades_C",
            "expectancy_A",
            "expectancy_B",
            "expectancy_C",
            "pf_A",
            "pf_B",
            "pf_C",
            "max_drawdown_A",
            "max_drawdown_B",
            "max_drawdown_C",
            "score_B",
            "trades_B_raw",
        }
        assert set(result.keys()) == expected_keys, f"Missing keys: {expected_keys - set(result.keys())}"

        assert isinstance(result["score_B"], (int, float))
        assert isinstance(result["trades_A"], int)
        assert isinstance(result["expectancy_B"], float)
        assert isinstance(result["pf_B"], float)
        assert isinstance(result["max_drawdown_B"], float)
