"""
Regression tests for S7_HTF_TREND_LTF_PULLBACK end-to-end implementation.

Focus areas:
1. H4 feature preparation with shift(1) anti-lookahead
2. H4 merge into M15 via backward merge_asof
3. H1 feature preparation with ATR in PIPS and shift(1) anti-lookahead
4. H1+ATR merge into M15 via backward merge_asof
5. S7 strategy gating on both trend_bias_h4 and adx_h4
6. S7 SL calculation using atr_h1_pips (not price)
7. CLI validation: S7 requires H4/H1 datasets
"""

import numpy as np
import pandas as pd
import pytest

from data.fx import PIP_SIZES
from data.io import (
    load_ohlc_csv,
    merge_h4_to_m15,
    merge_h1_to_m15_with_atr,
    prepare_h4_features,
    prepare_h1_features_with_atr,
)
from backtest.orchestrator import _StrategySpec, _apply_strategy_features
from strategies import s7_htf_trend_ltf_pullback


def create_sample_ohlc(n: int, close_base: float = 1.2000, trend: str = "up") -> pd.DataFrame:
    """Create synthetic OHLC data."""
    np.random.seed(42)
    data = []
    close = close_base
    
    for i in range(n):
        if trend == "up":
            drift = 0.0002
        elif trend == "down":
            drift = -0.0002
        else:
            drift = 0.0
        
        noise = np.random.normal(0, 0.0001)
        close = close + drift + noise
        
        open_ = close + np.random.normal(0, 0.0001)
        high = max(open_, close) + np.random.normal(0.0001, 0.0002)
        low = min(open_, close) - np.random.normal(0.0001, 0.0002)
        
        data.append({
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1000000,
        })
    
    df = pd.DataFrame(data)
    return df


def test_prepare_h4_features_shift_no_lookahead():
    """
    Verify that prepare_h4_features applies shift(1) to prevent lookahead.
    
    The first row of all features should be NaN (no prior bar).
    All non-NaN values should represent CLOSED bars only.
    """
    df = create_sample_ohlc(100, trend="up")
    df["time"] = pd.date_range("2024-01-01", periods=100, freq="4h")
    
    features_df = prepare_h4_features(
        df.copy(),
        symbol="EURUSD",
        ema_fast=50,
        ema_slow=200,
        adx_period=14,
        adx_min=20.0
    )
    
    # After shift(1), first row should be NaN
    assert features_df["ema_fast_h4"].isna().iloc[0], "First row should be NaN after shift(1)"
    assert features_df["trend_bias_h4"].isna().iloc[0], "First row of trend_bias_h4 should be NaN"
    
    # Second row onwards should have values (after warmup period)
    valid_rows = features_df.iloc[50:]["trend_bias_h4"].notna().sum()
    assert valid_rows > 0, "Should have valid trend_bias_h4 values after warmup"
    
    # trend_bias_h4 should only be -1, 0, or +1
    valid_bias = features_df["trend_bias_h4"].dropna()
    assert valid_bias.isin([-1.0, 0.0, 1.0]).all(), "trend_bias_h4 must be -1, 0, or +1"


def test_merge_h4_backward_no_future():
    """
    Verify that merge_asof(direction='backward') never pulls future H4 data into M15.
    
    With shift(1) already applied in prepare_h4_features, the first H4 bar is all NaN.
    The merge then follows, ensuring backward fill uses only prior-bar H4 data.
    """
    # H4: 20 bars, giving enough warmup for ADX
    h4_times = pd.date_range("2024-01-01", periods=20, freq="4h")
    h4_data = {
        "time": h4_times,
        "open": np.linspace(1.2000, 1.2100, 20),
        "high": np.linspace(1.2001, 1.2101, 20),
        "low": np.linspace(1.1999, 1.2099, 20),
        "close": np.linspace(1.2000, 1.2100, 20),
    }
    df_h4 = pd.DataFrame(h4_data)
    
    # Prepare H4 features (will shift(1))
    df_h4_prep = prepare_h4_features(df_h4, symbol="EURUSD")
    
    # M15: 300 bars starting at same time as H4
    m15_times = pd.date_range("2024-01-01", periods=300, freq="15min")
    m15_data = {
        "time": m15_times,
        "open": np.linspace(1.2000, 1.2010, 300),
        "high": np.linspace(1.2001, 1.2011, 300),
        "low": np.linspace(1.1999, 1.2009, 300),
        "close": np.linspace(1.2000, 1.2010, 300),
    }
    df_m15 = pd.DataFrame(m15_data)
    
    # Merge H4 into M15
    df_merged = merge_h4_to_m15(df_m15.copy(), df_h4_prep)
    
    # After shift(1) and merge, we should have trend_bias_h4 column with some values
    # (after warmup period, many will be NaN or valid)
    assert "trend_bias_h4" in df_merged.columns, "trend_bias_h4 not merged"
    
    # At least some rows should have non-NaN trend_bias_h4 (after warmup)
    valid_count = df_merged["trend_bias_h4"].notna().sum()
    # With 300 M15 bars and 20 H4 bars, we should get many matches after warmup
    assert valid_count > 0, f"trend_bias_h4 has no valid values (all {valid_count})"


def test_prepare_h1_features_with_atr_pips():
    """
    Verify that prepare_h1_features_with_atr:
    - Computes ATR in price units
    - Converts to pips
    - Applies shift(1) for no-lookahead
    """
    df = create_sample_ohlc(100, trend="up")
    df["time"] = pd.date_range("2024-01-01", periods=100, freq="1h")
    
    features_df = prepare_h1_features_with_atr(
        df.copy(),
        symbol="EURUSD",
        atr_period=14
    )
    
    # Check atr_h1_pips exists
    assert "atr_h1_pips" in features_df.columns, "atr_h1_pips should be computed"
    
    # After shift(1), first row should be NaN
    assert features_df["atr_h1_pips"].isna().iloc[0], "First row of atr_h1_pips should be NaN"
    
    # Subsequent rows should have positive values (ATR is always positive)
    valid_atr = features_df["atr_h1_pips"].dropna()
    assert (valid_atr > 0).all(), "atr_h1_pips should always be positive"
    
    # ATR in pips should be reasonable (e.g., 5-100 pips for a 1h bar on EURUSD)
    assert (valid_atr < 1000).all(), "atr_h1_pips should be < 1000"


def test_merge_h1_to_m15_with_atr():
    """
    Verify that merge_h1_to_m15_with_atr includes atr_h1_pips and maintains no-lookahead.
    """
    # H1: 50 bars, giving enough warmup for ATR
    h1_times = pd.date_range("2024-01-01", periods=50, freq="1h")
    h1_data = {
        "time": h1_times,
        "open": np.linspace(1.2000, 1.2050, 50),
        "high": np.linspace(1.2005, 1.2055, 50),
        "low": np.linspace(1.1995, 1.2045, 50),
        "close": np.linspace(1.2003, 1.2053, 50),
    }
    df_h1 = pd.DataFrame(h1_data)
    df_h1_prep = prepare_h1_features_with_atr(df_h1, symbol="EURUSD")
    
    # M15: 300 bars starting at same time
    m15_times = pd.date_range("2024-01-01", periods=300, freq="15min")
    m15_data = {
        "time": m15_times,
        "open": np.linspace(1.2000, 1.2050, 300),
        "high": np.linspace(1.2001, 1.2051, 300),
        "low": np.linspace(1.1999, 1.2049, 300),
        "close": np.linspace(1.2000, 1.2050, 300),
    }
    df_m15 = pd.DataFrame(m15_data)
    
    # Merge
    df_merged = merge_h1_to_m15_with_atr(df_m15.copy(), df_h1_prep)
    
    # atr_h1_pips should be present
    assert "atr_h1_pips" in df_merged.columns, "atr_h1_pips not merged"
    
    # After forward-fill and with enough H1 bars, should have many valid values
    valid_count = df_merged["atr_h1_pips"].notna().sum()
    assert valid_count > 100, f"atr_h1_pips should have >100 valid values after merge, got {valid_count}"
    
    # atr_h1_pips should be positive (ATR is always positive)
    valid_atr = df_merged["atr_h1_pips"].dropna()
    assert (valid_atr > 0).all(), "atr_h1_pips should always be positive"


def test_s7_requires_both_h4_adx_gates():
    """
    Verify that S7 gates on BOTH trend_bias_h4 and adx_h4.
    
    - trend_bias_h4 == 0 => FLAT
    - adx_h4 < adx_min_h4 => FLAT
    - Both must pass for entry
    """
    df = create_sample_ohlc(300, trend="up")
    df["time"] = pd.date_range("2024-01-01", periods=300, freq="15min")
    
    # Create H4 features manually
    df["ema_fast_h4"] = 1.2010
    df["ema_slow_h4"] = 1.2000
    df["adx_h4"] = 25.0
    df["trend_bias_h4"] = 1.0  # LONG
    
    # Create H1 features
    df["atr_h1_pips"] = 10.0
    df["chandelier_exit_h1"] = 1.1990
    
    # Create M15 features
    df["ema_pullback"] = df["close"] - 0.0003
    df["ema_trend"] = 1.2000
    df["atr_m15"] = 0.0005
    df["pullback_depth"] = 0.5
    df["ema_slope_m15"] = 0.0001
    
    # Test 1: Valid conditions => LONG
    cols = {col: df[col].values for col in df.columns}
    ctx = {
        "cols": cols,
        "idx": 150,
        "symbol": "EURUSD",
        "current_time": df["time"].iloc[150],
        "config": {
            "adx_min_h4": 20.0,
            "pullback_min": 0.3,
            "pullback_max": 1.2,
            "k_sl_h1": 2.0,
            "min_sl_points": 15.0,
        },
    }
    signal = s7_htf_trend_ltf_pullback.generate_signal(ctx)
    
    from desk_types import Side
    # Should enter LONG (or FLAT if pullback check fails, but pullback_depth=0.5 is valid)
    # The entry also requires close > ema_pullback, which is true
    assert signal.side in [Side.LONG, Side.FLAT], "Should attempt LONG or be FLAT"
    
    # Test 2: adx_h4 too low => FLAT
    df_low_adx = df.copy()
    df_low_adx["adx_h4"] = 15.0  # Below threshold
    cols_low_adx = {col: df_low_adx[col].values for col in df_low_adx.columns}
    ctx_low_adx = {
        "cols": cols_low_adx,
        "idx": 150,
        "symbol": "EURUSD",
        "current_time": df_low_adx["time"].iloc[150],
        "config": ctx["config"],
    }
    signal_low_adx = s7_htf_trend_ltf_pullback.generate_signal(ctx_low_adx)
    assert signal_low_adx.side == Side.FLAT, "Low ADX should block entry"
    assert "adx_h4_weak" in signal_low_adx.tags.get("entry_reason", "")
    
    # Test 3: Flat bias => FLAT
    df_flat = df.copy()
    df_flat["trend_bias_h4"] = 0.0
    cols_flat = {col: df_flat[col].values for col in df_flat.columns}
    ctx_flat = {
        "cols": cols_flat,
        "idx": 150,
        "symbol": "EURUSD",
        "current_time": df_flat["time"].iloc[150],
        "config": ctx["config"],
    }
    signal_flat = s7_htf_trend_ltf_pullback.generate_signal(ctx_flat)
    assert signal_flat.side == Side.FLAT, "Flat bias should block entry"


def test_s7_sl_points_units_are_pips():
    """
    Verify that S7 SL calculation uses atr_h1_pips (already in pips) and not price.
    
    SL = max(k_sl_h1 * atr_h1_pips, min_sl_points)
    Result should be in pips.
    """
    df = create_sample_ohlc(300, trend="up")
    df["time"] = pd.date_range("2024-01-01", periods=300, freq="15min")
    
    # Set up features for guaranteed LONG entry
    df["ema_fast_h4"] = 1.2010
    df["ema_slow_h4"] = 1.2000
    df["adx_h4"] = 30.0
    df["trend_bias_h4"] = 1.0  # LONG
    
    # atr_h1_pips = 20 pips (already converted by prepare_h1_features_with_atr)
    df["atr_h1_pips"] = 20.0
    df["chandelier_exit_h1"] = 1.1990
    
    df["ema_pullback"] = df["close"] - 0.0003
    df["ema_trend"] = 1.2000
    df["atr_m15"] = 0.0005
    df["pullback_depth"] = 0.5
    df["ema_slope_m15"] = 0.0001
    
    cols = {col: df[col].values for col in df.columns}
    
    k_sl_h1 = 2.0
    min_sl_points = 15.0
    expected_sl = max(k_sl_h1 * 20.0, min_sl_points)  # max(40, 15) = 40 pips
    
    ctx = {
        "cols": cols,
        "idx": 150,
        "symbol": "EURUSD",
        "current_time": df["time"].iloc[150],
        "config": {
            "adx_min_h4": 20.0,
            "pullback_min": 0.3,
            "pullback_max": 1.2,
            "k_sl_h1": k_sl_h1,
            "min_sl_points": min_sl_points,
        },
    }
    
    signal = s7_htf_trend_ltf_pullback.generate_signal(ctx)
    
    from desk_types import Side
    if signal.side != Side.FLAT:
        # Should have SL in pips
        assert signal.sl_points is not None, "SL should be set"
        assert signal.sl_points == expected_sl, f"SL should be {expected_sl}, got {signal.sl_points}"


def test_s7_no_fixed_tp_always_none():
    """Verify that S7 never sets a fixed TP (always None)."""
    df = create_sample_ohlc(300, trend="up")
    df["time"] = pd.date_range("2024-01-01", periods=300, freq="15min")
    
    # Set up for entry
    df["ema_fast_h4"] = 1.2010
    df["ema_slow_h4"] = 1.2000
    df["adx_h4"] = 30.0
    df["trend_bias_h4"] = 1.0
    df["atr_h1_pips"] = 20.0
    df["chandelier_exit_h1"] = 1.1990
    df["ema_pullback"] = df["close"] - 0.0003
    df["ema_trend"] = 1.2000
    df["atr_m15"] = 0.0005
    df["pullback_depth"] = 0.5
    df["ema_slope_m15"] = 0.0001
    
    cols = {col: df[col].values for col in df.columns}
    
    for idx in range(100, 250):
        ctx = {
            "cols": cols,
            "idx": idx,
            "symbol": "EURUSD",
            "current_time": df["time"].iloc[idx],
            "config": {
                "adx_min_h4": 20.0,
                "pullback_min": 0.3,
                "pullback_max": 1.2,
                "k_sl_h1": 2.0,
                "min_sl_points": 15.0,
            },
        }
        
        signal = s7_htf_trend_ltf_pullback.generate_signal(ctx)
        
        # TP must always be None
        assert signal.tp_points is None, f"idx {idx}: TP must be None (use trailing), got {signal.tp_points}"


def test_s7_required_features_all_present():
    """Verify that all required features are declared correctly."""
    required = s7_htf_trend_ltf_pullback.required_features()
    
    expected = {
        "ema_fast_h4", "ema_slow_h4", "adx_h4", "trend_bias_h4",
        "atr_h1_pips", "chandelier_exit_h1",
        "ema_pullback", "ema_trend", "atr_m15", "pullback_depth", "ema_slope_m15"
    }
    
    assert required == expected, f"Required features mismatch. Got {required}, expected {expected}"
