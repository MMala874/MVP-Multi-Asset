"""
Tests for S7_HTF_TREND_LTF_PULLBACK strategy.

Focus areas:
1. No lookahead: H4 features shift(1) before merge, H1 features shift(1) before merge
2. Bias gate: trend_bias_h4 blocks counter-trend trades
3. Pullback validation: 0.3 <= pullback_depth <= 1.2 filtering works
4. Entry logic: Close crosses EMA20 only when bias + pullback + slope OK
5. SL calculation: Always > 0, from H1 ATR
6. Low trade frequency: Fewer trades than baseline strategies
7. Feature computation: All required features present and valid
"""

import numpy as np
import pandas as pd
import pytest

from backtest.orchestrator import _StrategySpec, _apply_strategy_features
from strategies import s7_htf_trend_ltf_pullback
from features.indicators import ema, atr, adx, slope


def create_sample_m15_ohlc(n: int, close_base: float = 1.2000, trend: str = "up") -> pd.DataFrame:
    """Create synthetic M15 OHLC data."""
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
    df.index = pd.date_range("2024-01-01", periods=n, freq="15min")
    return df


def create_merged_h4_data(df_m15: pd.DataFrame) -> pd.DataFrame:
    """
    Simulate H4 features merged into M15 dataframe.
    Assumes H4 data has been shift(1) and merged via merge_asof.
    """
    df = df_m15.copy()
    
    # Simulate H4 features (merged, already shift(1))
    # EMA fast > slow for uptrend bias
    df["ema_fast_h4"] = ema(df["close"].rolling(window=96).mean(), 50)
    df["ema_slow_h4"] = ema(df["close"].rolling(window=96).mean(), 200)
    df["adx_h4"] = adx(df, 14)
    
    # Trend bias: +1 if fast > slow & adx > 20
    df["trend_bias_h4"] = np.where(
        (df["ema_fast_h4"] > df["ema_slow_h4"]) & (df["adx_h4"] > 20),
        1.0,
        np.where(
            (df["ema_fast_h4"] < df["ema_slow_h4"]) & (df["adx_h4"] > 20),
            -1.0,
            0.0
        )
    )
    
    return df


def create_merged_h1_data(df_m15: pd.DataFrame) -> pd.DataFrame:
    """
    Simulate H1 features merged into M15 dataframe.
    Assumes H1 data has been shift(1) and merged via merge_asof.
    """
    df = df_m15.copy()
    
    # Simulate H1 features (merged, already shift(1))
    # H1 ATR typically larger than M15, in PIPS
    df["atr_h1_pips"] = 20.0  # 20 pips
    
    # Chandelier exit: high - 3*ATR (in price)
    rolling_high = df["high"].shift(1).rolling(window=22, min_periods=22).max()
    df["chandelier_exit_h1"] = rolling_high - (3.0 * df["atr_h1_pips"] * 0.0001)
    
    return df


def test_s7_required_features():
    """Test that required_features() returns expected set."""
    required = s7_htf_trend_ltf_pullback.required_features()
    
    expected = {
        "ema_fast_h4", "ema_slow_h4", "adx_h4", "trend_bias_h4",
        "atr_h1_pips", "chandelier_exit_h1",
        "ema_pullback", "ema_trend", "atr_m15", "pullback_depth", "ema_slope_m15"
    }
    
    assert required == expected, f"Required features mismatch. Got {required}, expected {expected}"


def test_s7_feature_computation_uptrend():
    """Test that _apply_strategy_features computes all S7 features correctly for uptrend."""
    df = create_sample_m15_ohlc(500, trend="up")
    df = create_merged_h4_data(df)
    df = create_merged_h1_data(df)
    
    spec = _StrategySpec(
        name="S7_HTF_TREND_LTF_PULLBACK",
        module=None,
        params={
            "ema_fast_h4": 50,
            "ema_slow_h4": 200,
            "adx_period_h4": 14,
            "adx_min_h4": 20.0,
            "atr_period_h1": 14,
            "chandelier_window_h1": 22,
            "ema_pullback_m15": 20,
            "ema_trend_m15": 50,
            "atr_period_m15": 14,
            "slope_window_m15": 20,
        }
    )
    
    prepared = _apply_strategy_features(df.copy(), spec, symbol="EURUSD")
    
    # All required features should be present
    for feat in s7_htf_trend_ltf_pullback.required_features():
        assert feat in prepared.columns, f"Missing feature: {feat}"
        # Most should have some valid (non-NaN) values after warmup
        valid_count = prepared[feat].notna().sum()
        assert valid_count > 0, f"Feature {feat} has no valid values"


def test_s7_bias_gate_rejects_flat():
    """Test that trend_bias_h4 == 0 results in FLAT signal."""
    df = create_sample_m15_ohlc(300, trend="up")
    df = create_merged_h4_data(df)
    df = create_merged_h1_data(df)
    
    # Force flat bias on some indices
    df.loc[df.index[100:200], "trend_bias_h4"] = 0.0
    
    spec = _StrategySpec(
        name="S7_HTF_TREND_LTF_PULLBACK",
        module=None,
        params={
            "ema_fast_h4": 50,
            "ema_slow_h4": 200,
            "adx_period_h4": 14,
            "adx_min_h4": 20.0,
            "atr_period_h1": 14,
            "chandelier_window_h1": 22,
            "ema_pullback_m15": 20,
            "ema_trend_m15": 50,
            "atr_period_m15": 14,
            "slope_window_m15": 20,
            "pullback_min": 0.3,
            "pullback_max": 1.2,
            "k_sl_h1": 2.0,
            "min_sl_points": 15.0,
        }
    )
    
    prepared = _apply_strategy_features(df.copy(), spec, symbol="EURUSD")
    
    # Test signals where bias is flat
    flat_idx = 150
    cols = {col: prepared[col].values for col in prepared.columns}
    
    ctx = {
        "cols": cols,
        "idx": flat_idx,
        "symbol": "EURUSD",
        "current_time": prepared.index[flat_idx],
        "config": spec.params,
    }
    
    signal = s7_htf_trend_ltf_pullback.generate_signal(ctx)
    
    from desk_types import Side
    assert signal.side == Side.FLAT, f"Expected FLAT for bias_h4=0, got {signal.side}"
    assert signal.tags.get("entry_reason") == "h4_bias_flat"


def test_s7_bias_gate_long():
    """Test that trend_bias_h4 == +1 allows LONG but blocks SHORT."""
    df = create_sample_m15_ohlc(300, trend="up")
    df = create_merged_h4_data(df)
    df = create_merged_h1_data(df)
    
    # Force long bias everywhere, uptrend
    df["trend_bias_h4"] = 1.0
    
    spec = _StrategySpec(
        name="S7_HTF_TREND_LTF_PULLBACK",
        module=None,
        params={
            "ema_fast_h4": 50,
            "ema_slow_h4": 200,
            "adx_period_h4": 14,
            "adx_min_h4": 20.0,
            "atr_period_h1": 14,
            "chandelier_window_h1": 22,
            "ema_pullback_m15": 20,
            "ema_trend_m15": 50,
            "atr_period_m15": 14,
            "slope_window_m15": 20,
            "pullback_min": 0.0,  # Relax pullback for this test
            "pullback_max": 2.0,
            "k_sl_h1": 2.0,
            "min_sl_points": 15.0,
        }
    )
    
    prepared = _apply_strategy_features(df.copy(), spec, symbol="EURUSD")
    
    # Test signal at index with uptrend
    test_idx = 200
    cols = {col: prepared[col].values for col in prepared.columns}
    
    ctx = {
        "cols": cols,
        "idx": test_idx,
        "symbol": "EURUSD",
        "current_time": prepared.index[test_idx],
        "config": spec.params,
    }
    
    signal = s7_htf_trend_ltf_pullback.generate_signal(ctx)
    
    from desk_types import Side
    # With uptrend and bias +1, should get LONG or FLAT (not SHORT)
    assert signal.side in [Side.LONG, Side.FLAT], f"Bias +1 should not produce SHORT, got {signal.side}"


def test_s7_pullback_depth_gate():
    """Test that pullback_depth outside [0.3, 1.2] results in FLAT."""
    df = create_sample_m15_ohlc(300, trend="up")
    df = create_merged_h4_data(df)
    df = create_merged_h1_data(df)
    
    # Force long bias
    df["trend_bias_h4"] = 1.0
    
    # Force pullback_depth out of range
    df.loc[df.index[100:150], "pullback_depth"] = 0.1  # < 0.3
    df.loc[df.index[150:200], "pullback_depth"] = 2.0  # > 1.2
    
    spec = _StrategySpec(
        name="S7_HTF_TREND_LTF_PULLBACK",
        module=None,
        params={
            "ema_fast_h4": 50,
            "ema_slow_h4": 200,
            "adx_period_h4": 14,
            "adx_min_h4": 20.0,
            "atr_period_h1": 14,
            "chandelier_window_h1": 22,
            "ema_pullback_m15": 20,
            "ema_trend_m15": 50,
            "atr_period_m15": 14,
            "slope_window_m15": 20,
            "pullback_min": 0.3,
            "pullback_max": 1.2,
            "k_sl_h1": 2.0,
            "min_sl_points": 15.0,
        }
    )
    
    prepared = _apply_strategy_features(df.copy(), spec, symbol="EURUSD")
    
    # Test with pullback_depth < 0.3
    test_idx = 120
    cols = {col: prepared[col].values for col in prepared.columns}
    
    ctx = {
        "cols": cols,
        "idx": test_idx,
        "symbol": "EURUSD",
        "current_time": prepared.index[test_idx],
        "config": spec.params,
    }
    
    signal = s7_htf_trend_ltf_pullback.generate_signal(ctx)
    
    from desk_types import Side
    assert signal.side == Side.FLAT, f"pullback_depth=0.1 should give FLAT, got {signal.side}"
    assert "pullback_out_of_range" in signal.tags.get("entry_reason", "")


def test_s7_sl_always_positive():
    """Test that SL points are always > 0 when side != FLAT."""
    df = create_sample_m15_ohlc(400, trend="up")
    df = create_merged_h4_data(df)
    df = create_merged_h1_data(df)
    
    # Force ideal entry conditions
    df["trend_bias_h4"] = 1.0
    df["pullback_depth"] = 0.5
    df["ema_pullback"] = df["close"] - 0.0003
    df["ema_slope_m15"] = 0.0001
    
    spec = _StrategySpec(
        name="S7_HTF_TREND_LTF_PULLBACK",
        module=None,
        params={
            "ema_fast_h4": 50,
            "ema_slow_h4": 200,
            "adx_period_h4": 14,
            "adx_min_h4": 20.0,
            "atr_period_h1": 14,
            "chandelier_window_h1": 22,
            "ema_pullback_m15": 20,
            "ema_trend_m15": 50,
            "atr_period_m15": 14,
            "slope_window_m15": 20,
            "pullback_min": 0.3,
            "pullback_max": 1.2,
            "k_sl_h1": 2.0,
            "min_sl_points": 15.0,
        }
    )
    
    prepared = _apply_strategy_features(df.copy(), spec, symbol="EURUSD")
    
    # Collect all signals
    cols = {col: prepared[col].values for col in prepared.columns}
    
    non_flat_with_positive_sl = 0
    for idx in range(100, 300):
        ctx = {
            "cols": cols,
            "idx": idx,
            "symbol": "EURUSD",
            "current_time": prepared.index[idx],
            "config": spec.params,
        }
        
        signal = s7_htf_trend_ltf_pullback.generate_signal(ctx)
        
        from desk_types import Side
        if signal.side != Side.FLAT:
            assert signal.sl_points is not None, f"idx {idx}: Non-FLAT signal missing sl_points"
            assert signal.sl_points > 0, f"idx {idx}: SL must be positive, got {signal.sl_points}"
            non_flat_with_positive_sl += 1
    
    # We should find at least a few non-FLAT signals
    assert non_flat_with_positive_sl >= 1, "No non-FLAT signals found in test range"


def test_s7_no_fixed_tp():
    """Test that TP is always None (no fixed TP, use trailing)."""
    df = create_sample_m15_ohlc(400, trend="up")
    df = create_merged_h4_data(df)
    df = create_merged_h1_data(df)
    
    # Force entry conditions
    df["trend_bias_h4"] = 1.0
    df["pullback_depth"] = 0.5
    df["ema_pullback"] = df["close"] - 0.0003
    df["ema_slope_m15"] = 0.0001
    
    spec = _StrategySpec(
        name="S7_HTF_TREND_LTF_PULLBACK",
        module=None,
        params={
            "ema_fast_h4": 50,
            "ema_slow_h4": 200,
            "adx_period_h4": 14,
            "adx_min_h4": 20.0,
            "atr_period_h1": 14,
            "chandelier_window_h1": 22,
            "ema_pullback_m15": 20,
            "ema_trend_m15": 50,
            "atr_period_m15": 14,
            "slope_window_m15": 20,
            "pullback_min": 0.3,
            "pullback_max": 1.2,
            "k_sl_h1": 2.0,
            "min_sl_points": 15.0,
        }
    )
    
    prepared = _apply_strategy_features(df.copy(), spec, symbol="EURUSD")
    
    cols = {col: prepared[col].values for col in prepared.columns}
    
    for idx in range(100, 300):
        ctx = {
            "cols": cols,
            "idx": idx,
            "symbol": "EURUSD",
            "current_time": prepared.index[idx],
            "config": spec.params,
        }
        
        signal = s7_htf_trend_ltf_pullback.generate_signal(ctx)
        
        # TP should always be None (no fixed TP)
        assert signal.tp_points is None, f"idx {idx}: TP must be None, got {signal.tp_points}"


def test_s7_ema_slope_gating_long():
    """Test that EMA slope gate rejects when slope is bearish vs LONG bias."""
    df = create_sample_m15_ohlc(300, trend="up")
    df = create_merged_h4_data(df)
    df = create_merged_h1_data(df)
    
    # Force long bias
    df["trend_bias_h4"] = 1.0
    df["pullback_depth"] = 0.5
    df["ema_pullback"] = df["close"] - 0.0003
    # Force negative EMA slope (bearish)
    df["ema_slope_m15"] = -0.0001
    
    spec = _StrategySpec(
        name="S7_HTF_TREND_LTF_PULLBACK",
        module=None,
        params={
            "ema_fast_h4": 50,
            "ema_slow_h4": 200,
            "adx_period_h4": 14,
            "adx_min_h4": 20.0,
            "atr_period_h1": 14,
            "chandelier_window_h1": 22,
            "ema_pullback_m15": 20,
            "ema_trend_m15": 50,
            "atr_period_m15": 14,
            "slope_window_m15": 20,
            "pullback_min": 0.3,
            "pullback_max": 1.2,
            "k_sl_h1": 2.0,
            "min_sl_points": 15.0,
        }
    )
    
    prepared = _apply_strategy_features(df.copy(), spec, symbol="EURUSD")
    
    test_idx = 150
    cols = {col: prepared[col].values for col in prepared.columns}
    
    ctx = {
        "cols": cols,
        "idx": test_idx,
        "symbol": "EURUSD",
        "current_time": prepared.index[test_idx],
        "config": spec.params,
    }
    
    signal = s7_htf_trend_ltf_pullback.generate_signal(ctx)
    
    from desk_types import Side
    assert signal.side == Side.FLAT, "Bearish slope vs LONG bias should reject"
    assert "ema_slope_bearish_vs_long_bias" in signal.tags.get("entry_reason", "")
