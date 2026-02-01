"""
Tests for S3_TS_MOM_VOL_REGIME strategy signal generation.
"""

import numpy as np
import pandas as pd
import pytest

from desk_types import Side
from strategies.s3_ts_mom_vol_regime import (
    generate_signal,
    required_features,
    STRATEGY_ID,
)


# ============ FIXTURES ============

@pytest.fixture
def mock_config():
    """Mock config object with strategy params."""
    class MockConfig:
        class Strategies:
            params = {
                "S3_TS_MOM_VOL_REGIME": {
                    "mom_window": 48,
                    "mom_th": 0.0,
                    "atr_short_period": 14,
                    "atr_long_period": 100,
                    "vol_ratio_th": 1.1,
                    "atr_min_pips": 8.0,
                    "allowed_vol_regimes": ["MID", "HIGH"],
                    "spike_block": False,
                    "k_sl": 2.5,
                    "min_sl_points": 8.0,
                    "k_tp": None,
                }
            }
        strategies = Strategies()
    
    return MockConfig()


# ============ HELPER FUNCTIONS ============

def _create_simple_arrays(size=150, base_mom=0.0):
    """
    Create simple test arrays for momentum signals.
    
    Returns:
        dict with mom, vol_ratio, atr_pips, regime_snapshot arrays
    """
    idx_start = 50  # Valid data starts here
    
    # Create momentum array (NaN before idx_start)
    mom = np.full(size, np.nan)
    mom[idx_start:] = base_mom
    
    # Create vol_ratio (constant high value)
    vol_ratio = np.full(size, 1.5)
    
    # Create atr_pips (constant medium value)
    atr_pips = np.full(size, 15.0)
    
    # Create regime_snapshot array (all HIGH)
    regime_snapshot = np.full(size, "VOL=HIGH|SPIKE=0", dtype=object)
    
    return {
        "mom": mom.copy(),
        "vol_ratio": vol_ratio.copy(),
        "atr_pips": atr_pips.copy(),
        "regime_snapshot": regime_snapshot.copy(),
    }


def _make_context(cols, idx, symbol, current_time, config=None, regime_snapshot="VOL=HIGH|SPIKE=0"):
    """
    Helper to create context dict for signal generation.
    """
    if config is not None:
        config_dict = config.strategies.params.get("S3_TS_MOM_VOL_REGIME", {})
    else:
        config_dict = {}
    
    return {
        "cols": cols,
        "idx": idx,
        "symbol": symbol,
        "current_time": current_time,
        "config": config_dict,
        "regime_snapshot": regime_snapshot,
    }


# ============ TESTS ============

def test_required_features():
    """Test that required_features returns expected columns."""
    features = required_features()
    assert isinstance(features, list)
    assert "mom" in features
    assert "vol_ratio" in features
    assert "atr_pips" in features
    assert "regime_snapshot" in features


def test_no_lookahead_momentum():
    """
    Test anti-lookahead property: Changing future momentum value
    should NOT affect signal at current index.
    """
    # Create test arrays
    arrays = _create_simple_arrays(size=150, base_mom=0.001)
    idx = 100
    
    # Generate signal with original momentum
    ctx_original = _make_context(
        cols={
            "mom": arrays["mom"].copy(),
            "vol_ratio": arrays["vol_ratio"].copy(),
            "atr_pips": arrays["atr_pips"].copy(),
            "regime_snapshot": "VOL=HIGH|SPIKE=0",
        },
        idx=idx,
        symbol="EURUSD",
        current_time=pd.Timestamp("2024-01-01 12:00"),
        config=None,
        regime_snapshot="VOL=HIGH|SPIKE=0",
    )
    
    signal_original = generate_signal(ctx_original)
    
    # Modify future momentum (idx + 10)
    arrays_modified = _create_simple_arrays(size=150, base_mom=0.001)
    arrays_modified["mom"][idx + 10] = 0.999  # Large future change
    
    ctx_modified = _make_context(
        cols={
            "mom": arrays_modified["mom"].copy(),
            "vol_ratio": arrays_modified["vol_ratio"].copy(),
            "atr_pips": arrays_modified["atr_pips"].copy(),
            "regime_snapshot": "VOL=HIGH|SPIKE=0",
        },
        idx=idx,
        symbol="EURUSD",
        current_time=pd.Timestamp("2024-01-01 12:00"),
        config=None,
        regime_snapshot="VOL=HIGH|SPIKE=0",
    )
    
    signal_modified = generate_signal(ctx_modified)
    
    # Signals should be identical (no lookahead)
    assert signal_original.side == signal_modified.side
    assert signal_original.sl_points == signal_modified.sl_points


def test_momentum_sanity_nan_period(mock_config):
    """
    Test that momentum NaN values result in FLAT signals.
    """
    arrays = _create_simple_arrays(size=150)
    idx_nan = 20  # Before valid data starts (NaN region)
    
    ctx = _make_context(
        cols={
            "mom": arrays["mom"].copy(),
            "vol_ratio": arrays["vol_ratio"].copy(),
            "atr_pips": arrays["atr_pips"].copy(),
            "regime_snapshot": "VOL=HIGH|SPIKE=0",
        },
        idx=idx_nan,
        symbol="EURUSD",
        current_time=pd.Timestamp("2024-01-01 12:00"),
        config=mock_config,
        regime_snapshot="VOL=HIGH|SPIKE=0",
    )
    
    signal = generate_signal(ctx)
    
    # Should be FLAT due to NaN momentum
    assert signal.side == Side.FLAT
    assert signal.tags.get("status") == "mom_nan"


def test_signal_long_on_positive_momentum(mock_config):
    """Test that LONG signal is generated when momentum > threshold."""
    arrays = _create_simple_arrays(size=150, base_mom=0.002)
    idx = 100
    
    ctx = _make_context(
        cols={
            "mom": arrays["mom"].copy(),
            "vol_ratio": arrays["vol_ratio"].copy(),
            "atr_pips": arrays["atr_pips"].copy(),
            "regime_snapshot": "VOL=HIGH|SPIKE=0",
        },
        idx=idx,
        symbol="EURUSD",
        current_time=pd.Timestamp("2024-01-01 12:00"),
        config=mock_config,
        regime_snapshot="VOL=HIGH|SPIKE=0",
    )
    
    signal = generate_signal(ctx)
    
    assert signal.side == Side.LONG
    assert signal.sl_points > 0
    assert signal.tags.get("status") == "signal_generated"


def test_signal_short_on_negative_momentum(mock_config):
    """Test that SHORT signal is generated when momentum < -threshold."""
    arrays = _create_simple_arrays(size=150, base_mom=-0.002)
    idx = 100
    
    ctx = _make_context(
        cols={
            "mom": arrays["mom"].copy(),
            "vol_ratio": arrays["vol_ratio"].copy(),
            "atr_pips": arrays["atr_pips"].copy(),
            "regime_snapshot": "VOL=HIGH|SPIKE=0",
        },
        idx=idx,
        symbol="EURUSD",
        current_time=pd.Timestamp("2024-01-01 12:00"),
        config=mock_config,
        regime_snapshot="VOL=HIGH|SPIKE=0",
    )
    
    signal = generate_signal(ctx)
    
    assert signal.side == Side.SHORT
    assert signal.sl_points > 0
    assert signal.tags.get("status") == "signal_generated"


def test_signal_flat_on_neutral_momentum(mock_config):
    """Test that FLAT signal when momentum is at threshold."""
    arrays = _create_simple_arrays(size=150, base_mom=0.0)
    idx = 100
    
    ctx = _make_context(
        cols={
            "mom": arrays["mom"].copy(),
            "vol_ratio": arrays["vol_ratio"].copy(),
            "atr_pips": arrays["atr_pips"].copy(),
            "regime_snapshot": "VOL=HIGH|SPIKE=0",
        },
        idx=idx,
        symbol="EURUSD",
        current_time=pd.Timestamp("2024-01-01 12:00"),
        config=mock_config,
        regime_snapshot="VOL=HIGH|SPIKE=0",
    )
    
    signal = generate_signal(ctx)
    
    assert signal.side == Side.FLAT
    assert signal.tags.get("status") == "momentum_neutral"


def test_signal_rejects_low_vol_regime(mock_config):
    """Test that signal is rejected when vol regime is not in allowed_vol_regimes."""
    arrays = _create_simple_arrays(size=150, base_mom=0.002)
    idx = 100
    
    ctx = _make_context(
        cols={
            "mom": arrays["mom"].copy(),
            "vol_ratio": arrays["vol_ratio"].copy(),
            "atr_pips": arrays["atr_pips"].copy(),
            "regime_snapshot": "VOL=LOW|SPIKE=0",
        },
        idx=idx,
        symbol="EURUSD",
        current_time=pd.Timestamp("2024-01-01 12:00"),
        config=mock_config,
        regime_snapshot="VOL=LOW|SPIKE=0",  # LOW not allowed
    )
    
    signal = generate_signal(ctx)
    
    assert signal.side == Side.FLAT
    assert signal.tags.get("status") == "vol_regime_reject"


def test_signal_rejects_low_vol_ratio(mock_config):
    """Test that signal is rejected when vol_ratio < threshold."""
    arrays = _create_simple_arrays(size=150, base_mom=0.002)
    arrays["vol_ratio"][:] = 0.9  # Below threshold (vol_ratio_th = 1.1)
    idx = 100
    
    ctx = _make_context(
        cols={
            "mom": arrays["mom"].copy(),
            "vol_ratio": arrays["vol_ratio"].copy(),
            "atr_pips": arrays["atr_pips"].copy(),
            "regime_snapshot": "VOL=HIGH|SPIKE=0",
        },
        idx=idx,
        symbol="EURUSD",
        current_time=pd.Timestamp("2024-01-01 12:00"),
        config=mock_config,
        regime_snapshot="VOL=HIGH|SPIKE=0",
    )
    
    signal = generate_signal(ctx)
    
    assert signal.side == Side.FLAT
    assert signal.tags.get("status") == "vol_ratio_reject"


def test_signal_rejects_low_atr_pips(mock_config):
    """Test that signal is rejected when atr_pips < minimum."""
    arrays = _create_simple_arrays(size=150, base_mom=0.002)
    arrays["atr_pips"][:] = 5.0  # Below minimum (atr_min_pips = 8.0)
    idx = 100
    
    ctx = _make_context(
        cols={
            "mom": arrays["mom"].copy(),
            "vol_ratio": arrays["vol_ratio"].copy(),
            "atr_pips": arrays["atr_pips"].copy(),
            "regime_snapshot": "VOL=HIGH|SPIKE=0",
        },
        idx=idx,
        symbol="EURUSD",
        current_time=pd.Timestamp("2024-01-01 12:00"),
        config=mock_config,
        regime_snapshot="VOL=HIGH|SPIKE=0",
    )
    
    signal = generate_signal(ctx)
    
    assert signal.side == Side.FLAT
    assert signal.tags.get("status") == "atr_pips_reject"


def test_signal_spike_block(mock_config):
    """Test that signal is blocked when spike_block=True and SPIKE=1."""
    mock_config.strategies.params["S3_TS_MOM_VOL_REGIME"]["spike_block"] = True
    
    arrays = _create_simple_arrays(size=150, base_mom=0.002)
    idx = 100
    
    ctx = _make_context(
        cols={
            "mom": arrays["mom"].copy(),
            "vol_ratio": arrays["vol_ratio"].copy(),
            "atr_pips": arrays["atr_pips"].copy(),
            "regime_snapshot": "VOL=HIGH|SPIKE=1",
        },
        idx=idx,
        symbol="EURUSD",
        current_time=pd.Timestamp("2024-01-01 12:00"),
        config=mock_config,
        regime_snapshot="VOL=HIGH|SPIKE=1",
    )
    
    signal = generate_signal(ctx)
    
    assert signal.side == Side.FLAT
    assert signal.tags.get("status") == "spike_reject"


def test_sl_points_calculation(mock_config):
    """Test that SL is correctly calculated as max(k_sl * atr_pips, min_sl_points)."""
    arrays = _create_simple_arrays(size=150, base_mom=0.002)
    arrays["atr_pips"][:] = 15.0  # Fixed 15 pips
    idx = 100
    
    # k_sl = 2.5, min_sl_points = 8.0
    # sl_points = max(2.5 * 15.0, 8.0) = max(37.5, 8.0) = 37.5
    expected_sl = max(2.5 * 15.0, 8.0)
    
    ctx = _make_context(
        cols={
            "mom": arrays["mom"].copy(),
            "vol_ratio": arrays["vol_ratio"].copy(),
            "atr_pips": arrays["atr_pips"].copy(),
            "regime_snapshot": "VOL=HIGH|SPIKE=0",
        },
        idx=idx,
        symbol="EURUSD",
        current_time=pd.Timestamp("2024-01-01 12:00"),
        config=mock_config,
        regime_snapshot="VOL=HIGH|SPIKE=0",
    )
    
    signal = generate_signal(ctx)
    
    assert signal.side == Side.LONG
    assert np.isclose(signal.sl_points, expected_sl, rtol=1e-6)


def test_sl_points_floor_with_min(mock_config):
    """Test that SL respects min_sl_points floor."""
    arrays = _create_simple_arrays(size=150, base_mom=0.002)
    arrays["atr_pips"][:] = 8.5  # 8.5 pips (passes atr_min_pips = 8.0)
    idx = 100
    
    # k_sl = 2.5, min_sl_points = 8.0
    # sl_points = max(2.5 * 8.5, 8.0) = max(21.25, 8.0) = 21.25
    expected_sl = max(2.5 * 8.5, 8.0)
    
    ctx = _make_context(
        cols={
            "mom": arrays["mom"].copy(),
            "vol_ratio": arrays["vol_ratio"].copy(),
            "atr_pips": arrays["atr_pips"].copy(),
            "regime_snapshot": "VOL=HIGH|SPIKE=0",
        },
        idx=idx,
        symbol="EURUSD",
        current_time=pd.Timestamp("2024-01-01 12:00"),
        config=mock_config,
        regime_snapshot="VOL=HIGH|SPIKE=0",
    )
    
    signal = generate_signal(ctx)
    
    assert signal.side == Side.LONG
    assert np.isclose(signal.sl_points, expected_sl, rtol=1e-6)


def test_missing_required_column(mock_config):
    """Test that signal is FLAT when required column is missing."""
    arrays = _create_simple_arrays(size=150, base_mom=0.002)
    idx = 100
    
    ctx = _make_context(
        cols={
            # Missing 'mom' column
            "vol_ratio": arrays["vol_ratio"].copy(),
            "atr_pips": arrays["atr_pips"].copy(),
            "regime_snapshot": "VOL=HIGH|SPIKE=0",
        },
        idx=idx,
        symbol="EURUSD",
        current_time=pd.Timestamp("2024-01-01 12:00"),
        config=mock_config,
        regime_snapshot="VOL=HIGH|SPIKE=0",
    )
    
    signal = generate_signal(ctx)
    
    assert signal.side == Side.FLAT
    assert signal.tags.get("status") == "missing_col"


def test_idx_out_of_bounds(mock_config):
    """Test that signal is FLAT when idx is out of bounds."""
    arrays = _create_simple_arrays(size=150, base_mom=0.002)
    idx = 999  # Out of bounds
    
    ctx = _make_context(
        cols={
            "mom": arrays["mom"].copy(),
            "vol_ratio": arrays["vol_ratio"].copy(),
            "atr_pips": arrays["atr_pips"].copy(),
            "regime_snapshot": "VOL=HIGH|SPIKE=0",
        },
        idx=idx,
        symbol="EURUSD",
        current_time=pd.Timestamp("2024-01-01 12:00"),
        config=mock_config,
        regime_snapshot="VOL=HIGH|SPIKE=0",
    )
    
    signal = generate_signal(ctx)
    
    assert signal.side == Side.FLAT
    assert signal.tags.get("status") == "idx_error"
