"""
Integration test: S7 CLI validation and H4/H1 requirement enforcement.
"""

import pytest
from configs.loader import load_config
from configs.models import Config
import tempfile
import pandas as pd
import numpy as np


def create_temp_ohlc_csv(n: int = 100) -> str:
    """Create temporary OHLC CSV file and return path."""
    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="15min"),
        "open": np.linspace(1.2000, 1.2100, n),
        "high": np.linspace(1.2001, 1.2101, n),
        "low": np.linspace(1.1999, 1.2099, n),
        "close": np.linspace(1.2000, 1.2100, n),
    })
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        df.to_csv(f, index=False)
        return f.name


def test_s7_cli_requires_h4_h1():
    """
    Test that enabling S7 without H4/H1 datasets raises ValueError.
    
    This simulates the run_backtest validation logic.
    """
    from scripts.run_backtest import _load_symbols
    import argparse
    
    # Load config with S7 enabled
    cfg = load_config("configs/examples/example_config.yaml")
    
    # Create mock args without H4/H1
    args = argparse.Namespace(
        eurusd="eurusd_m15.csv",
        eurusd_h1=None,  # Missing H1
        eurusd_h4=None,  # Missing H4
        gbpusd=None,
        gbpusd_h1=None,
        gbpusd_h4=None,
        usdjpy=None,
        usdjpy_h1=None,
        usdjpy_h4=None,
    )
    
    # Enable S7 in config
    cfg_dict = cfg.model_dump()
    cfg_dict["strategies"]["enabled"] = ["S7_HTF_TREND_LTF_PULLBACK"]
    cfg = Config(**cfg_dict)
    
    # Mock files (they don't need to exist for the validation check to trigger)
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
        args.eurusd = f.name
        f.write(b"time,open,high,low,close\n2024-01-01 00:00,1.2000,1.2001,1.1999,1.2000\n")
    
    # Should raise ValueError because S7 requires both H4 and H1
    with pytest.raises(ValueError) as exc_info:
        _load_symbols(args, cfg)
    
    assert "S7_HTF_TREND_LTF_PULLBACK requires" in str(exc_info.value)


def test_s7_atr_h1_pips_in_config():
    """
    Test that S7 config includes all required H4/H1 parameters for proper merging.
    """
    cfg = load_config("configs/examples/example_config.yaml")
    
    # Get S7 parameters
    s7_params = cfg.strategies.params.get("S7_HTF_TREND_LTF_PULLBACK", {})
    
    # Verify H4 parameters exist
    assert "ema_fast_h4" in s7_params, "Missing ema_fast_h4"
    assert "ema_slow_h4" in s7_params, "Missing ema_slow_h4"
    assert "adx_min_h4" in s7_params, "Missing adx_min_h4"
    assert "adx_period_h4" in s7_params, "Missing adx_period_h4"
    
    # Verify H1 parameters exist
    assert "atr_period_h1" in s7_params, "Missing atr_period_h1"
    assert "k_sl_h1" in s7_params, "Missing k_sl_h1"
    assert "min_sl_points" in s7_params, "Missing min_sl_points"
    
    # Verify M15 parameters exist
    assert "pullback_min" in s7_params, "Missing pullback_min"
    assert "pullback_max" in s7_params, "Missing pullback_max"


def test_prepare_h4_features_outputs_correct_bias():
    """Test that H4 bias computation is correct."""
    from data.io import prepare_h4_features
    
    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=300, freq="4h"),
        "open": np.linspace(1.2000, 1.2300, 300),
        "high": np.linspace(1.2001, 1.2301, 300),
        "low": np.linspace(1.1999, 1.2299, 300),
        "close": np.linspace(1.2000, 1.2300, 300),
    })
    
    features = prepare_h4_features(df, symbol="EURUSD", adx_min=20.0)
    
    # Check bias is only -1, 0, or +1 after warmup
    bias_valid = features["trend_bias_h4"].dropna()
    assert bias_valid.isin([-1.0, 0.0, 1.0]).all(), "trend_bias_h4 must be -1, 0, or +1"
    
    # Check ADX exists
    adx_valid = features["adx_h4"].dropna()
    assert (adx_valid >= 0).all(), "ADX must be >= 0"


def test_prepare_h1_features_with_atr_pips_units():
    """Test that H1 ATR is correctly converted to pips."""
    from data.io import prepare_h1_features_with_atr
    from data.fx import PIP_SIZES
    
    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=100, freq="1h"),
        "open": np.linspace(1.2000, 1.2100, 100),
        "high": np.linspace(1.2005, 1.2105, 100),
        "low": np.linspace(1.1995, 1.2095, 100),
        "close": np.linspace(1.2000, 1.2100, 100),
    })
    
    features = prepare_h1_features_with_atr(df, symbol="EURUSD", atr_period=14)
    
    # After shift(1), first value is NaN
    assert features["atr_h1_pips"].isna().iloc[0], "First value should be NaN after shift(1)"
    
    # Subsequent values should be positive pips
    valid_atr = features["atr_h1_pips"].dropna()
    assert (valid_atr > 0).all(), "atr_h1_pips must be positive"
    
    # Sanity check: for EURUSD with pip_size=0.0001, typical ATR should be 5-100 pips
    # (depends on volatility, but let's check it's reasonable)
    assert (valid_atr < 1000).all(), "atr_h1_pips should be < 1000"
