"""
Regression test: _apply_strategy_features receives symbol parameter.
Ensures NameError for 'symbol' is resolved in S4 strategy feature prep.
"""

import numpy as np
import pandas as pd
import pytest

from backtest.orchestrator import BacktestOrchestrator
from configs.loader import load_config


def test_orchestrator_s4_with_symbol_parameter_no_nameerror():
    """
    Minimal test: Load OHLC data, enable S4_TREND_COND_MEAN_REVERSION,
    run orchestrator, and verify NameError: 'symbol' is not raised.
    """
    # Create minimal OHLC data
    dates = pd.date_range("2024-01-01", periods=100, freq="15min")
    eurusd_df = pd.DataFrame({
        "time": dates,
        "open": 1.0800 + np.random.uniform(-0.0010, 0.0010, 100),
        "high": 1.0810 + np.random.uniform(-0.0005, 0.0015, 100),
        "low": 1.0790 + np.random.uniform(-0.0015, 0.0005, 100),
        "close": 1.0805 + np.random.uniform(-0.0010, 0.0010, 100),
    })
    eurusd_df["high"] = eurusd_df[["open", "high", "low", "close"]].max(axis=1)
    eurusd_df["low"] = eurusd_df[["open", "high", "low", "close"]].min(axis=1)
    
    # Load real config to get all required params
    config = load_config("configs/examples/example_config.yaml")
    
    # Run orchestrator with S4 - should NOT raise NameError
    orchestrator = BacktestOrchestrator()
    try:
        trades, report = orchestrator.run(
            df_by_symbol={"EURUSD": eurusd_df},
            config=config,
            scenarios=["A"],
        )
        # If we get here, no NameError was raised
        assert trades is not None
        assert isinstance(trades, pd.DataFrame)
    except NameError as e:
        if "symbol" in str(e):
            pytest.fail(f"NameError for 'symbol' should be fixed: {e}")
        raise


if __name__ == "__main__":
    test_orchestrator_s4_with_symbol_parameter_no_nameerror()
    print("✓ Test passed: S4 orchestrator runs without NameError")
