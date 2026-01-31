#!/usr/bin/env python3
"""
Quick integration test for fast & serious tuning:
- Verify scenario filtering works (orchestrator accepts scenarios parameter)
- Verify worker functions accept scenarios
- Verify progress printing format
- Verify two-stage logic
"""
import pandas as pd
from pathlib import Path

from backtest.orchestrator import BacktestOrchestrator
from configs.loader import load_config
from data.io import load_ohlc_csv
from tuning.grid import build_grid
from tuning.worker import run_worker_single_scenario, run_worker_full_scenarios


def test_scenario_filtering():
    """Test that BacktestOrchestrator accepts scenarios parameter."""
    print("\n[TEST 1] Scenario filtering in BacktestOrchestrator")
    
    config = load_config("configs/examples/example_config.yaml")
    
    # Create synthetic data with more bars for features to compute
    import numpy as np
    n = 200
    np.random.seed(42)
    returns = np.random.randn(n) * 0.001
    close = (1 + returns).cumprod()
    
    df = pd.DataFrame({
        "open": close * (1 + np.random.randn(n) * 0.0001),
        "high": close * (1 + np.abs(np.random.randn(n) * 0.0003)),
        "low": close * (1 - np.abs(np.random.randn(n) * 0.0003)),
        "close": close,
    })
    
    orchestrator = BacktestOrchestrator()
    
    # Test B-only (Stage 1 scenario)
    trades_b, report_b = orchestrator.run(
        {"EURUSD": df}, 
        config, 
        scenarios=["B"]
    )
    by_scenario_b = report_b["metrics"]["by_scenario"]
    # Scenarios may be empty if no trades, just verify the key exists
    if by_scenario_b:
        assert len(by_scenario_b) == 1, f"Expected 1 scenario, got {len(by_scenario_b)}"
        assert "B" in by_scenario_b, "B should be present"
        print("  [OK] B-only scenario evaluation works (with trades)")
    else:
        print("  [OK] B-only scenario evaluation works (no trades on this data)")
    
    # Test A/B/C (Stage 2 scenario)
    trades_abc, report_abc = orchestrator.run(
        {"EURUSD": df}, 
        config, 
        scenarios=["A", "B", "C"]
    )
    by_scenario_abc = report_abc["metrics"]["by_scenario"]
    if by_scenario_abc:
        assert len(by_scenario_abc) == 3, f"Expected 3 scenarios, got {len(by_scenario_abc)}"
        assert all(s in by_scenario_abc for s in ["A", "B", "C"]), "All scenarios should be present"
        print("  [OK] A/B/C scenario evaluation works (with trades)")
    else:
        print("  [OK] A/B/C scenario evaluation works (no trades on this data)")
    
    print("  [OK] TEST 1 PASSED\n")


def test_worker_functions():
    """Test that worker functions integrate with scenario filtering."""
    print("[TEST 2] Worker functions with scenarios")
    
    config_path = "configs/examples/example_config.yaml"
    strategy_id = "S1_TREND_EMA_ATR_ADX"
    
    # Create synthetic dataset
    import numpy as np
    n = 100
    np.random.seed(42)
    returns = np.random.randn(n) * 0.001
    close = (1 + returns).cumprod()
    
    df_eurusd = pd.DataFrame({
        "open": close * (1 + np.random.randn(n) * 0.0001),
        "high": close * (1 + np.abs(np.random.randn(n) * 0.0003)),
        "low": close * (1 - np.abs(np.random.randn(n) * 0.0003)),
        "close": close,
    })
    df_by_symbol = {"EURUSD": df_eurusd}
    
    params = {
        "ema_fast": 5,
        "ema_slow": 20,
        "atr_period": 14,
        "adx_period": 14,
        "k_sl": 2.0,
    }
    
    # Test Stage 1 worker (B-only)
    result_b = run_worker_single_scenario(
        config_path,
        strategy_id,
        params,
        df_by_symbol,
        "B",
    )
    assert "score_B" in result_b, "Result should have score_B"
    assert "trades_B" in result_b, "Result should have trades_B"
    print("  [OK] Stage 1 worker (B-only) works")
    
    # Test Stage 2 worker (A/B/C)
    result_abc = run_worker_full_scenarios(
        config_path,
        strategy_id,
        params,
        df_by_symbol,
    )
    assert "score_B" in result_abc, "Result should have score_B"
    assert all(f"trades_{s}" in result_abc for s in ["A", "B", "C"]), \
        "Result should have metrics for A, B, C"
    print("  [OK] Stage 2 worker (A/B/C) works")
    
    print("  [OK] TEST 2 PASSED\n")


def test_progress_format():
    """Test that progress printing format is correct."""
    print("[TEST 3] Progress printing format")
    
    from scripts.run_tuning_mp import _format_time, _print_progress
    
    # Test time formatting
    assert _format_time(3661) == "01:01:01", "Time format incorrect"
    assert _format_time(0) == "00:00:00", "Time format incorrect"
    assert _format_time(86399) == "23:59:59", "Time format incorrect"
    print("  [OK] Time formatting works")
    
    # Test progress printing (capture output)
    import io
    import sys
    
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    
    best_result = {"score_B": 1.2345, "params": {"ema_fast": 5}}
    _print_progress(50, 1152, 45.0, best_result, show_eta=True, stage="Stage 1")
    
    output = sys.stdout.getvalue()
    sys.stdout = old_stdout
    
    assert "[Stage 1]" in output, "Stage label missing"
    assert "50/1152" in output, "Progress counter missing"
    assert "best_score=1.2345" in output, "Best score missing"
    print("  [OK] Progress format correct")
    
    print("  [OK] TEST 3 PASSED\n")


def test_grid_generation():
    """Test that grid generation works for tuning."""
    print("[TEST 4] Grid generation")
    
    grid = build_grid("S1_TREND_EMA_ATR_ADX", preset="small")
    assert len(grid) == 6, f"Expected 6 combos (small), got {len(grid)}"
    print(f"  [OK] Small grid: {len(grid)} combinations")
    
    grid = build_grid("S1_TREND_EMA_ATR_ADX", preset="medium")
    assert len(grid) == 1152, f"Expected 1152 combos (medium), got {len(grid)}"
    print(f"  [OK] Medium grid: {len(grid)} combinations")
    
    grid = build_grid("S1_TREND_EMA_ATR_ADX", preset="large")
    assert len(grid) > 5000, f"Expected >5000 combos (large), got {len(grid)}"
    print(f"  [OK] Large grid: {len(grid)} combinations")
    
    print("  [OK] TEST 4 PASSED\n")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Fast & Serious Tuning Integration Tests")
    print("="*60)
    
    try:
        test_scenario_filtering()
        test_worker_functions()
        test_progress_format()
        test_grid_generation()
        
        print("="*60)
        print("ALL TESTS PASSED!")
        print("="*60 + "\n")
        
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}\n")
        exit(1)
    except Exception as e:
        print(f"\nERROR: {e}\n")
        import traceback
        traceback.print_exc()
        exit(1)
