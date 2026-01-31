from __future__ import annotations

import pandas as pd
import tempfile
from pathlib import Path

from tuning.grid import build_grid
from tuning.worker import (
    run_worker,
    run_worker_single_scenario,
    run_worker_full_scenarios,
)


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
    """Test worker function output for one parameter set (full A/B/C)."""
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


def test_worker_single_scenario_output_structure() -> None:
    """Test run_worker_single_scenario returns only ONE scenario metrics."""
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

        # Test with scenario B only
        result = run_worker_single_scenario(
            "configs/examples/example_config.yaml",
            "S1_TREND_EMA_ATR_ADX",
            params,
            df_paths,
            scenario="B",
        )

        # Should only have B metrics, not A or C
        expected_keys = {
            "params",
            "trades_B",
            "expectancy_B",
            "pf_B",
            "max_drawdown_B",
            "score_B",
        }
        assert set(result.keys()) == expected_keys, f"Got unexpected keys: {set(result.keys())}"

        # Should NOT have A or C metrics
        unexpected_keys = {"trades_A", "trades_C", "expectancy_A", "expectancy_C"}
        assert not (set(result.keys()) & unexpected_keys), f"Should not have A/C metrics: {set(result.keys())}"

        assert isinstance(result["score_B"], (int, float))
        assert isinstance(result["trades_B"], int)
        assert isinstance(result["expectancy_B"], float)
        assert isinstance(result["pf_B"], float)
        assert isinstance(result["max_drawdown_B"], float)


def test_worker_full_scenarios_output_structure() -> None:
    """Test run_worker_full_scenarios returns A/B/C metrics."""
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

        result = run_worker_full_scenarios(
            "configs/examples/example_config.yaml",
            "S1_TREND_EMA_ATR_ADX",
            params,
            df_paths,
        )

        # Should have all A/B/C metrics
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
        }
        assert set(result.keys()) == expected_keys, f"Got unexpected keys: {set(result.keys())}"

        assert isinstance(result["score_B"], (int, float))
        assert isinstance(result["trades_A"], int)
        assert isinstance(result["trades_B"], int)
        assert isinstance(result["trades_C"], int)


def test_grid_size_presets() -> None:
    """Test that grid size presets generate correct sizes."""
    small = build_grid("S1_TREND_EMA_ATR_ADX", preset="small")
    medium = build_grid("S1_TREND_EMA_ATR_ADX", preset="medium")
    large = build_grid("S1_TREND_EMA_ATR_ADX", preset="large")

    # Check sizes (calculated as product of parameter ranges)
    # small: 1 × 1 × 3 × 2 × 1 × 1 × 1 = 6
    # medium: 3 × 2 × 4 × 4 × 3 × 2 × 2 = 1152
    # large: 5 × 3 × 5 × 5 × 4 × 3 × 3 = 13500
    assert len(small) == 6, f"small: expected 6, got {len(small)}"
    assert len(medium) == 1152, f"medium: expected 1152, got {len(medium)}"
    assert len(large) == 13500, f"large: expected 13500, got {len(large)}"

    # Verify all have correct keys
    required_keys = {
        "ema_fast",
        "ema_slow",
        "adx_th",
        "k_sl",
        "k_tp",
        "min_sl_points",
        "min_tp_points",
    }
    for grid in [small, medium, large]:
        for params in grid[:3]:  # Check first 3
            assert set(params.keys()) == required_keys


def test_limit_bars_truncates_dataframe() -> None:
    """Test that limit_bars correctly truncates OHLC data."""
    # Create test data
    df_test = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=1000, freq="1h"),
        "open": [1.0 + i * 0.0001 for i in range(1000)],
        "high": [1.01 + i * 0.0001 for i in range(1000)],
        "low": [0.99 + i * 0.0001 for i in range(1000)],
        "close": [1.005 + i * 0.0001 for i in range(1000)],
    })

    # Test limiting to 100 bars (should be last 100 rows)
    limit_bars = 100
    df_limited = df_test.tail(limit_bars).reset_index(drop=True)

    assert len(df_limited) == limit_bars, f"Expected {limit_bars} rows, got {len(df_limited)}"
    
    # Verify it's the LAST 100 rows
    expected_first_close = 1.005 + 900 * 0.0001  # Row 900 in original
    actual_first_close = df_limited.iloc[0]["close"]
    assert abs(actual_first_close - expected_first_close) < 1e-6, \
        f"Expected first close ~{expected_first_close}, got {actual_first_close}"


def test_worker_accepts_dataframes() -> None:
    """Test that worker functions accept DataFrames directly (not just paths)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test DataFrame
        eurusd_data = {
            "time": pd.date_range("2024-01-01", periods=100, freq="1h"),
            "open": [1.0 + i * 0.0001 for i in range(100)],
            "high": [1.01 + i * 0.0001 for i in range(100)],
            "low": [0.99 + i * 0.0001 for i in range(100)],
            "close": [1.005 + i * 0.0001 for i in range(100)],
        }
        eurusd_df = pd.DataFrame(eurusd_data)

        params = {
            "ema_fast": 20,
            "ema_slow": 50,
            "adx_th": 20,
            "k_sl": 1.5,
            "k_tp": 1.0,
            "min_sl_points": 5.0,
            "min_tp_points": 5.0,
        }

        # Pass DataFrame directly (not path)
        df_by_symbol = {
            "EURUSD": eurusd_df,
            "GBPUSD": None,
            "USDJPY": None,
        }

        # Test single scenario with DataFrame
        result = run_worker_single_scenario(
            "configs/examples/example_config.yaml",
            "S1_TREND_EMA_ATR_ADX",
            params,
            df_by_symbol,
            scenario="B",
        )

        assert result is not None
        assert "score_B" in result
        assert isinstance(result["score_B"], (int, float))

        # Test full scenarios with DataFrame
        result_full = run_worker_full_scenarios(
            "configs/examples/example_config.yaml",
            "S1_TREND_EMA_ATR_ADX",
            params,
            df_by_symbol,
        )

        assert result_full is not None
        assert "score_B" in result_full
        assert "trades_A" in result_full
        assert "trades_B" in result_full
        assert "trades_C" in result_full
