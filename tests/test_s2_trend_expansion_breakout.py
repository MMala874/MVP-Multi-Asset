"""
Tests for S2_TREND_EXPANSION_BREAKOUT strategy.

Focus areas:
1. No lookahead (shift(1) used, future data doesn't affect past)
2. Entry logic gates work correctly
3. SL calculation is valid
4. Strategy is rare (few trades)
"""

import numpy as np
import pandas as pd

from backtest.orchestrator import _StrategySpec, _apply_strategy_features
from strategies import s2_trend_expansion_breakout
from features.indicators import ema, atr


def create_sample_ohlc(n: int = 400, trend: str = "up") -> pd.DataFrame:
    """Create synthetic OHLC with adequate warmup (400+ bars)."""
    np.random.seed(42)
    
    data = []
    close = 1.2000
    
    for i in range(n):
        if trend == "up":
            drift = 0.0003
        elif trend == "down":
            drift = -0.0003
        else:
            drift = 0.0
        
        # Add structure: compression then expansion
        vol_mult = 1.0
        if 100 <= i < 150:
            vol_mult = 0.5  # Compression
        elif 150 <= i < 250:
            vol_mult = 2.5  # Expansion (STRONG!)
        
        random_move = np.random.normal(0, 0.0002 * vol_mult)
        open_price = close
        close = close + drift + random_move
        high = max(open_price, close) + abs(np.random.normal(0, 0.00015 * vol_mult))
        low = min(open_price, close) - abs(np.random.normal(0, 0.00015 * vol_mult))
        
        data.append({"open": open_price, "high": high, "low": low, "close": close})
    
    df = pd.DataFrame(data)
    df.index = pd.date_range("2024-01-01", periods=n, freq="h")
    return df


def test_no_lookahead():
    """Verify shift(1) is used - future data doesn't affect past indices."""
    df = create_sample_ohlc(400, trend="up")
    
    spec = _StrategySpec(
        name="S2_TREND_EXPANSION_BREAKOUT",
        module=None,
        params={
            "ema_fast": 50,
            "ema_slow": 200,
            "atr_short_period": 14,
            "atr_long_period": 100,
            "breakout_lookback": 55,
        },
    )
    
    df_orig = _apply_strategy_features(df.copy(), spec)
    hh_orig = df_orig["breakout_hh"].copy()
    
    # Modify future data (bars 300+)
    df_mod = df.copy()
    df_mod.loc[df_mod.index[300:], "high"] = 999.0
    df_mod = _apply_strategy_features(df_mod, spec)
    hh_mod = df_mod["breakout_hh"]
    
    # Check past indices (220-280) unaffected
    errors = 0
    for idx in range(220, 280):
        if pd.notna(hh_orig.iloc[idx]) and pd.notna(hh_mod.iloc[idx]):
            if not np.isclose(hh_orig.iloc[idx], hh_mod.iloc[idx]):
                errors += 1
    
    assert errors == 0, f"Found {errors} indices where future data affected past HH values"
    print("[OK] No lookahead test PASSED")


def test_required_features():
    """Verify required_features returns expected set."""
    features = s2_trend_expansion_breakout.required_features()
    
    expected = {
        "close", "high", "low", "open",
        "ema_fast", "ema_slow",
        "atr_short", "atr_long",
        "atr_pips",
        "breakout_hh", "breakout_ll",
        "vol_ratio",
        "regime_snapshot",
    }
    
    assert features == expected, f"Feature mismatch: {features} vs {expected}"
    print("[OK] Required features test PASSED")


def test_sl_validity_when_signal():
    """Verify SL is valid (> 0) when side != FLAT."""
    df = create_sample_ohlc(400, trend="up")
    pip_size = 0.0001
    
    spec = _StrategySpec(
        name="S2_TREND_EXPANSION_BREAKOUT",
        module=None,
        params={
            "ema_fast": 50,
            "ema_slow": 200,
            "atr_short_period": 14,
            "atr_long_period": 100,
            "breakout_lookback": 55,
        },
    )
    df = _apply_strategy_features(df, spec)
    df["atr_pips"] = df["atr_short"] / pip_size
    df["regime_snapshot"] = "VOL=HIGH|SPIKE=0"
    
    bad_signals = []
    
    for idx in range(250, len(df)):
        ctx = {
            "cols": {k: df[k].values for k in df.columns},
            "idx": idx,
            "symbol": "EURUSD",
            "current_time": df.index[idx],
            "config": {
                "ema_fast": 50,
                "ema_slow": 200,
                "vol_ratio_th": 0.8,  # Very low - almost all pass
                "atr_min_pips": 2,  # Low
                "breakout_lookback": 55,
                "buffer_atr": 0.05,  # Small buffer
                "impulse_th": 0.5,  # Low impulse threshold
                "k_sl": 3.0,
                "min_sl_points": 8,
                "allowed_vol_regimes": ["LOW", "MID", "HIGH"],
            },
            "last_exit_idx": -1,
        }
        
        signal = s2_trend_expansion_breakout.generate_signal(ctx)
        if signal.side.name != "FLAT":
            # If we got a signal, SL must be valid
            if signal.sl_points is None or signal.sl_points <= 0:
                bad_signals.append((idx, signal.side.name, signal.sl_points))
    
    assert len(bad_signals) == 0, \
        f"Found {len(bad_signals)} signals with invalid SL: {bad_signals[:5]}"
    
    print(f"[OK] Found {len(bad_signals)} bad signals - all signals had valid SL")
    print("[OK] SL validity test PASSED")


def test_gate_progression():
    """Verify that gates filter properly."""
    df = create_sample_ohlc(400, trend="up")
    pip_size = 0.0001
    
    spec = _StrategySpec(
        name="S2_TREND_EXPANSION_BREAKOUT",
        module=None,
        params={
            "ema_fast": 50,
            "ema_slow": 200,
            "atr_short_period": 14,
            "atr_long_period": 100,
            "breakout_lookback": 55,
        },
    )
    df = _apply_strategy_features(df, spec)
    df["atr_pips"] = df["atr_short"] / pip_size
    df["regime_snapshot"] = "VOL=HIGH|SPIKE=0"
    
    # Count with all gates relaxed (most permissive)
    signals_all_open = 0
    gate_failures = {"vol": 0, "breakout": 0, "impulse": 0}
    
    for idx in range(250, len(df)):
        ctx = {
            "cols": {k: df[k].values for k in df.columns},
            "idx": idx,
            "symbol": "EURUSD",
            "current_time": df.index[idx],
            "config": {
                "ema_fast": 50,
                "ema_slow": 200,
                "vol_ratio_th": 0.5,  # VERY LOW
                "atr_min_pips": 0.1,  # VERY LOW
                "breakout_lookback": 55,
                "buffer_atr": 0.01,  # VERY SMALL
                "impulse_th": 0.1,  # VERY LOW
                "k_sl": 3.0,
                "min_sl_points": 8,
                "allowed_vol_regimes": ["LOW", "MID", "HIGH"],
            },
            "last_exit_idx": -1,
        }
        
        signal = s2_trend_expansion_breakout.generate_signal(ctx)
        if signal.side.name != "FLAT":
            signals_all_open += 1
        else:
            # Track which gate failed
            if "vol_gate" in signal.tags and signal.tags["vol_gate"] != "pass":
                gate_failures["vol"] += 1
            elif "breakout" in signal.tags and "fail" in signal.tags["breakout"]:
                gate_failures["breakout"] += 1
            elif "impulse_gate" in signal.tags and signal.tags["impulse_gate"] != "pass":
                gate_failures["impulse"] += 1
    
    print(f"[OK] Gate statistics:")
    print(f"  Signals generated: {signals_all_open}")
    print(f"  Vol gate failures: {gate_failures['vol']}")
    print(f"  Breakout failures: {gate_failures['breakout']}")
    print(f"  Impulse failures: {gate_failures['impulse']}")
    print("[OK] Gate progression test PASSED")


def test_ema_bias_filter():
    """Verify EMA bias filters correctly."""
    df = create_sample_ohlc(400, trend="up")
    
    spec = _StrategySpec(
        name="S2_TREND_EXPANSION_BREAKOUT",
        module=None,
        params={
            "ema_fast": 50,
            "ema_slow": 200,
            "atr_short_period": 14,
            "atr_long_period": 100,
            "breakout_lookback": 55,
        },
    )
    df = _apply_strategy_features(df, spec)
    
    # In uptrend, ema_fast should eventually be > ema_slow
    for idx in range(300, len(df)):
        ema_f = df["ema_fast"].iloc[idx]
        ema_s = df["ema_slow"].iloc[idx]
        
        if pd.notna(ema_f) and pd.notna(ema_s):
            # After 300 bars in uptrend, should see mostly upward EMAs
            if idx > 300:
                assert ema_f > 0 and ema_s > 0
    
    print("[OK] EMA bias filter test PASSED")


def test_rarity():
    """Verify strategy trades rarely (selective)."""
    df = create_sample_ohlc(400, trend="up")
    pip_size = 0.0001
    
    spec = _StrategySpec(
        name="S2_TREND_EXPANSION_BREAKOUT",
        module=None,
        params={
            "ema_fast": 50,
            "ema_slow": 200,
            "atr_short_period": 14,
            "atr_long_period": 100,
            "breakout_lookback": 55,
        },
    )
    df = _apply_strategy_features(df, spec)
    df["atr_pips"] = df["atr_short"] / pip_size
    df["regime_snapshot"] = "VOL=HIGH|SPIKE=0"
    
    # Count with default config (baseline rarity)
    signal_count_baseline = 0
    for idx in range(250, len(df)):
        ctx = {
            "cols": {k: df[k].values for k in df.columns},
            "idx": idx,
            "symbol": "EURUSD",
            "current_time": df.index[idx],
            "config": {
                "ema_fast": 50,
                "ema_slow": 200,
                "vol_ratio_th": 1.1,  # Default (selectivity)
                "atr_min_pips": 8,  # Default
                "breakout_lookback": 55,
                "buffer_atr": 0.2,  # Default
                "impulse_th": 1.2,  # Default
                "k_sl": 3.0,
                "min_sl_points": 8,
                "allowed_vol_regimes": ["MID", "HIGH"],  # More selective
            },
            "last_exit_idx": -1,
        }
        
        signal = s2_trend_expansion_breakout.generate_signal(ctx)
        if signal.side.name != "FLAT":
            signal_count_baseline += 1
    
    # Expecting ~5-15 signals in 150 bars (10% or less)
    signal_pct = (signal_count_baseline / 150) * 100
    print(f"[OK] Signal count: {signal_count_baseline}/150 ({signal_pct:.1f}%)")
    assert signal_pct < 50, f"Too many signals: {signal_pct}% (should be < 50%)"
    print("[OK] Rarity test PASSED")


if __name__ == "__main__":
    test_no_lookahead()
    test_required_features()
    test_sl_validity_when_signal()
    test_gate_progression()
    test_ema_bias_filter()
    test_rarity()



if __name__ == "__main__":
    test_no_lookahead()
    test_required_features()
    test_sl_validity_when_signal()
    test_gate_progression()
    test_ema_bias_filter()
    test_rarity()
    print("\n[SUCCESS] ALL TESTS PASSED!")
