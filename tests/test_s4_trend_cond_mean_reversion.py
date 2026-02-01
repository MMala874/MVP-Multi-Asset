"""
Regression tests for S4 trend-conditioned mean reversion strategy.

Tests:
- Anti-lookahead for mr_z computation
- H1 bias gating (direction filtering)
- SL validation (always present)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.orchestrator import BacktestOrchestrator
from configs.loader import load_config
from desk_types import Side
from strategies.s4_trend_cond_mean_reversion import generate_signal


class TestS4AntiLookahead:
    """Verify anti-lookahead for Z-score computation."""
    
    def test_mr_z_unchanged_with_future_close_change(self):
        """
        Z-score should not change if future close values are modified.
        
        Modifying close[t+10] should NOT affect mr_z[t].
        """
        # Create synthetic data
        n_bars = 100
        df = pd.DataFrame({
            "time": pd.date_range("2024-01-01", periods=n_bars, freq="15min"),
            "open": np.linspace(1.1000, 1.1500, n_bars),
            "high": np.linspace(1.1100, 1.1600, n_bars),
            "low": np.linspace(1.0900, 1.1400, n_bars),
            "close": np.linspace(1.1010, 1.1510, n_bars),
        })
        
        # Compute MR features normally
        ema_base_period = 20
        z_window = 10
        
        ema_base = df["close"].ewm(span=ema_base_period, adjust=False).mean()
        mr_delta = df["close"] - ema_base
        rolling = mr_delta.rolling(window=z_window, min_periods=z_window)
        mean = rolling.mean()
        std = rolling.std(ddof=0)
        mr_z_original = (mr_delta - mean) / std
        mr_z_original[std == 0] = np.nan
        
        # Store MR values at specific bars
        idx_check = 50
        z_before = mr_z_original.iloc[idx_check]
        
        # Now modify future close values (lookahead violation if not anti-lookahead)
        df_modified = df.copy()
        df_modified.loc[idx_check + 10:, "close"] = df_modified.loc[idx_check + 10:, "close"] * 1.05
        
        # Recompute MR with modified data
        ema_base_mod = df_modified["close"].ewm(span=ema_base_period, adjust=False).mean()
        mr_delta_mod = df_modified["close"] - ema_base_mod
        rolling_mod = mr_delta_mod.rolling(window=z_window, min_periods=z_window)
        mean_mod = rolling_mod.mean()
        std_mod = rolling_mod.std(ddof=0)
        mr_z_modified = (mr_delta_mod - mean_mod) / std_mod
        mr_z_modified[std_mod == 0] = np.nan
        
        z_after = mr_z_modified.iloc[idx_check]
        
        # Because we use rolling.mean() and rolling.std() without looking into the future,
        # the value at idx_check should be the same (or very close) before/after.
        # (Exact match if windowing only uses past data up to and including idx_check)
        assert np.isclose(z_before, z_after, rtol=1e-6, equal_nan=True), \
            f"Z-score at idx {idx_check} changed when future close modified. Before: {z_before}, After: {z_after}"
    
    def test_mr_z_only_uses_past_data(self):
        """
        mr_z at index t should only depend on data at t and earlier.
        
        With min_periods set to z_window, rolling window starts at t-(z_window-1).
        """
        n_bars = 50
        df = pd.DataFrame({
            "close": np.random.randn(n_bars).cumsum() + 100,
        })
        
        z_window = 10
        ema_base = df["close"].ewm(span=20, adjust=False).mean()
        mr_delta = df["close"] - ema_base
        rolling = mr_delta.rolling(window=z_window, min_periods=z_window)
        mean = rolling.mean()
        std = rolling.std(ddof=0)
        mr_z = (mr_delta - mean) / std
        
        # At idx=20, the rolling window uses data from idx 11-20 (not beyond)
        idx_test = 20
        window_start = idx_test - z_window + 1  # 11
        window_end = idx_test + 1  # 21 (exclusive)
        
        # Manually compute mean and std for this window
        manual_mean = mr_delta.iloc[window_start:idx_test + 1].mean()
        manual_std = mr_delta.iloc[window_start:idx_test + 1].std(ddof=0)
        manual_z = (mr_delta.iloc[idx_test] - manual_mean) / manual_std if manual_std > 0 else np.nan
        
        assert np.isclose(mr_z.iloc[idx_test], manual_z, rtol=1e-10, equal_nan=True), \
            "mr_z at idx {idx_test} does not match manual computation with past window only"


class TestS4H1BiaGating:
    """Verify H1 bias correctly gates entry directions."""
    
    def test_long_bias_blocks_short_entry(self):
        """When H1 bias = +1 (LONG), strategy must not return SHORT even if mr_z signals short."""
        # Create context with LONG bias but SHORT z-signal
        cols = {
            "mr_z": np.array([0.0] * 50 + [2.5] + [0.0] * 50),  # idx 50 has strong SHORT z-signal
            "trend_bias_h1": np.array([1.0] * 101),  # LONG bias throughout
            "adx_m15": np.array([10.0] * 101),  # Low ADX (gate passes)
            "ema_slope": np.array([0.00001] * 101),  # Small slope (gate passes)
            "atr_pips": np.array([10.0] * 101),
        }
        
        ctx = {
            "cols": cols,
            "idx": 50,
            "config": {
                "z_entry": 1.5,
                "use_h1_bias": True,
                "adx_max_m15": 18.0,
                "slope_th": 0.00003,
                "k_sl": 2.5,
                "min_sl_points": 8.0,
            },
            "symbol": "EURUSD",
            "current_time": None,
        }
        
        signal = generate_signal(ctx)
        # With mr_z=2.5 and bias=+1, should be FLAT (bias gates SHORT)
        assert signal.side == Side.FLAT, \
            f"LONG bias should block SHORT entry, but got {signal.side}"
    
    def test_short_bias_blocks_long_entry(self):
        """When H1 bias = -1 (SHORT), strategy must not return LONG even if mr_z signals long."""
        cols = {
            "mr_z": np.array([0.0] * 50 + [-2.5] + [0.0] * 50),  # idx 50 has strong LONG z-signal
            "trend_bias_h1": np.array([-1.0] * 101),  # SHORT bias throughout
            "adx_m15": np.array([10.0] * 101),  # Low ADX (gate passes)
            "ema_slope": np.array([0.00001] * 101),  # Small slope (gate passes)
            "atr_pips": np.array([10.0] * 101),
        }
        
        ctx = {
            "cols": cols,
            "idx": 50,
            "config": {
                "z_entry": 1.5,
                "use_h1_bias": True,
                "adx_max_m15": 18.0,
                "slope_th": 0.00003,
                "k_sl": 2.5,
                "min_sl_points": 8.0,
            },
            "symbol": "EURUSD",
            "current_time": None,
        }
        
        signal = generate_signal(ctx)
        # With mr_z=-2.5 and bias=-1, should be FLAT (bias gates LONG)
        assert signal.side == Side.FLAT, \
            f"SHORT bias should block LONG entry, but got {signal.side}"
    
    def test_flat_bias_blocks_all_entries(self):
        """When H1 bias = 0 (FLAT), strategy must return FLAT regardless of z-signal."""
        cols = {
            "mr_z": np.array([0.0] * 50 + [-2.5] + [0.0] * 50),  # Strong LONG z-signal
            "trend_bias_h1": np.array([0.0] * 101),  # FLAT bias throughout
            "adx_m15": np.array([10.0] * 101),  # Low ADX (gate passes)
            "ema_slope": np.array([0.00001] * 101),  # Small slope (gate passes)
            "atr_pips": np.array([10.0] * 101),
        }
        
        ctx = {
            "cols": cols,
            "idx": 50,
            "config": {
                "z_entry": 1.5,
                "use_h1_bias": True,
                "adx_max_m15": 18.0,
                "slope_th": 0.00003,
                "k_sl": 2.5,
                "min_sl_points": 8.0,
            },
            "symbol": "EURUSD",
            "current_time": None,
        }
        
        signal = generate_signal(ctx)
        # With bias=0, should be FLAT even though mr_z signals LONG
        assert signal.side == Side.FLAT, \
            f"FLAT bias should block all entries, but got {signal.side}"
    
    def test_no_h1_bias_allows_both_directions(self):
        """With use_h1_bias=false, z-score alone should determine direction."""
        # Test LONG entry
        cols_long = {
            "mr_z": np.array([0.0] * 50 + [-2.5] + [0.0] * 50),  # LONG z-signal
            "trend_bias_h1": np.array([np.nan] * 101),  # No bias (NaN)
            "adx_m15": np.array([10.0] * 101),  # Low ADX
            "ema_slope": np.array([0.00001] * 101),  # Small slope
            "atr_pips": np.array([10.0] * 101),
        }
        
        ctx_long = {
            "cols": cols_long,
            "idx": 50,
            "config": {
                "z_entry": 1.5,
                "use_h1_bias": False,
                "adx_max_m15": 18.0,
                "slope_th": 0.00003,
                "k_sl": 2.5,
                "min_sl_points": 8.0,
            },
            "symbol": "EURUSD",
            "current_time": None,
        }
        
        signal_long = generate_signal(ctx_long)
        assert signal_long.side == Side.LONG, \
            f"Without H1 bias, LONG z-signal should generate LONG entry, got {signal_long.side}"
        
        # Test SHORT entry
        cols_short = {
            "mr_z": np.array([0.0] * 50 + [2.5] + [0.0] * 50),  # SHORT z-signal
            "trend_bias_h1": np.array([np.nan] * 101),
            "adx_m15": np.array([10.0] * 101),
            "ema_slope": np.array([0.00001] * 101),
            "atr_pips": np.array([10.0] * 101),
        }
        
        ctx_short = {
            "cols": cols_short,
            "idx": 50,
            "config": {
                "z_entry": 1.5,
                "use_h1_bias": False,
                "adx_max_m15": 18.0,
                "slope_th": 0.00003,
                "k_sl": 2.5,
                "min_sl_points": 8.0,
            },
            "symbol": "EURUSD",
            "current_time": None,
        }
        
        signal_short = generate_signal(ctx_short)
        assert signal_short.side == Side.SHORT, \
            f"Without H1 bias, SHORT z-signal should generate SHORT entry, got {signal_short.side}"


class TestS4SLValidation:
    """Verify stop-loss is always present for valid entries."""
    
    def test_sl_present_on_long_entry(self):
        """Long entries must have sl_points > 0."""
        cols = {
            "mr_z": np.array([0.0] * 50 + [-2.0] + [0.0] * 50),
            "trend_bias_h1": np.array([1.0] * 101),
            "adx_m15": np.array([10.0] * 101),
            "ema_slope": np.array([0.00001] * 101),
            "atr_pips": np.array([10.0] * 101),
        }
        
        ctx = {
            "cols": cols,
            "idx": 50,
            "config": {
                "z_entry": 1.5,
                "use_h1_bias": True,
                "adx_max_m15": 18.0,
                "slope_th": 0.00003,
                "k_sl": 2.5,
                "min_sl_points": 8.0,
            },
            "symbol": "EURUSD",
            "current_time": None,
        }
        
        signal = generate_signal(ctx)
        assert signal.side == Side.LONG
        assert signal.sl_points is not None
        assert signal.sl_points > 0, f"SL should be > 0, got {signal.sl_points}"
    
    def test_sl_present_on_short_entry(self):
        """Short entries must have sl_points > 0."""
        cols = {
            "mr_z": np.array([0.0] * 50 + [2.0] + [0.0] * 50),
            "trend_bias_h1": np.array([-1.0] * 101),
            "adx_m15": np.array([10.0] * 101),
            "ema_slope": np.array([0.00001] * 101),
            "atr_pips": np.array([10.0] * 101),
        }
        
        ctx = {
            "cols": cols,
            "idx": 50,
            "config": {
                "z_entry": 1.5,
                "use_h1_bias": True,
                "adx_max_m15": 18.0,
                "slope_th": 0.00003,
                "k_sl": 2.5,
                "min_sl_points": 8.0,
            },
            "symbol": "EURUSD",
            "current_time": None,
        }
        
        signal = generate_signal(ctx)
        assert signal.side == Side.SHORT
        assert signal.sl_points is not None
        assert signal.sl_points > 0, f"SL should be > 0, got {signal.sl_points}"
    
    def test_tp_optional_but_valid_when_present(self):
        """TP can be None, but if k_tp provided and > 0, should be valid."""
        cols = {
            "mr_z": np.array([0.0] * 50 + [-2.0] + [0.0] * 50),
            "trend_bias_h1": np.array([1.0] * 101),
            "adx_m15": np.array([10.0] * 101),
            "ema_slope": np.array([0.00001] * 101),
            "atr_pips": np.array([10.0] * 101),
        }
        
        ctx = {
            "cols": cols,
            "idx": 50,
            "config": {
                "z_entry": 1.5,
                "use_h1_bias": True,
                "adx_max_m15": 18.0,
                "slope_th": 0.00003,
                "k_sl": 2.5,
                "min_sl_points": 8.0,
                "k_tp": 1.5,
                "min_tp_points": 5.0,
            },
            "symbol": "EURUSD",
            "current_time": None,
        }
        
        signal = generate_signal(ctx)
        assert signal.side == Side.LONG
        assert signal.tp_points is not None
        assert signal.tp_points > 0, f"TP should be > 0 when k_tp provided, got {signal.tp_points}"


class TestS4Integration:
    """Integration tests with real config loading."""
    
    def test_strategy_in_allowed_strategies(self):
        """Verify S4 is registered in config models."""
        from configs.models import ALLOWED_STRATEGIES
        assert "S4_TREND_COND_MEAN_REVERSION" in ALLOWED_STRATEGIES
    
    def test_strategy_loads_from_config(self):
        """Verify S4 config loads without validation errors."""
        config = load_config("configs/examples/example_config.yaml")
        assert config is not None
        
        # Should have S4 in allowed strategies (or at least params should exist)
        s4_params = config.strategies.params.get("S4_TREND_COND_MEAN_REVERSION")
        assert s4_params is not None, "S4 params not in config"
        
        # Verify key parameters exist
        assert "ema_base_period" in s4_params
        assert "z_window" in s4_params
        assert "z_entry" in s4_params
        assert "use_h1_bias" in s4_params
        assert "k_sl" in s4_params
