"""
Regression test for atr_pips computation in _prepare_features.
Verifies that atr is computed even when strategy only uses atr_short/atr_long.
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path

# Append workspace to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.orchestrator import BacktestOrchestrator, _prepare_features, _StrategySpec
from configs.models import Config, Universe, BarContract, Strategies, Risk, RiskCaps, Regime, Costs, SlippageModel, Validation, WalkForward, MonteCarlo, MonteCarlo1, MonteCarlo2, Reproducibility, Outputs


def _create_minimal_ohlc(num_bars: int = 100) -> pd.DataFrame:
    """Create minimal OHLC DataFrame."""
    np.random.seed(42)
    returns = np.random.normal(0.0001, 0.002, num_bars)
    close = 1.0500 * np.exp(np.cumsum(returns))
    
    open_price = close + np.random.normal(0, 0.0002, num_bars)
    high = np.maximum(close, open_price) + np.abs(np.random.normal(0, 0.0003, num_bars))
    low = np.minimum(close, open_price) - np.abs(np.random.normal(0, 0.0003, num_bars))
    volume = np.ones(num_bars) * 1e6
    
    dates = pd.date_range(start="2023-01-01", periods=num_bars, freq="15min")
    
    df = pd.DataFrame({
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)
    return df


def _create_s2_only_config() -> Config:
    """Create config with only S2_TREND_EXPANSION_BREAKOUT enabled."""
    return Config(
        universe=Universe(symbols=["EURGBP"], timeframe="M15"),
        bar_contract=BarContract(signal_on="close", fill_on="open_next", allow_bar0=False),
        strategies=Strategies(
            enabled=["S2_TREND_EXPANSION_BREAKOUT"],
            params={
                "S2_TREND_EXPANSION_BREAKOUT": {
                    "ema_fast": 50,
                    "ema_slow": 200,
                    "atr_short_period": 14,
                    "atr_long_period": 100,
                    "breakout_lookback": 55,
                    "buffer_atr": 0.2,
                    "vol_ratio_th": 1.1,
                    "impulse_th": 1.2,
                    "k_sl": 3.0,
                    "min_sl_points": 8.0,
                    "k_trail": 3.5,
                    "max_hold_bars": 96,
                    "min_mfe_atr": 0.5,
                },
                "S1_TREND_EMA_ATR_ADX": {},
                "S1_TREND_BREAKOUT_DONCHIAN": {},
                "S1_TREND_BREAKOUT_RETEST": {},
                "S2_MR_ZSCORE_EMA_REGIME": {},
                "S3_BREAKOUT_ATR_REGIME_EMA200": {},
            }
        ),
        risk=Risk(
            r_base=1.0,
            caps=RiskCaps(per_strategy=100000.0, per_symbol=100000.0, usd_exposure_cap=500000.0),
            conflict_policy="netting",
            priority_order=None,
            dd_day_limit=1.0,
            dd_week_limit=1.0,
            max_execution_errors=10,
        ),
        costs=Costs(
            spread_baseline_pips={"EURGBP": 0.0001},
            slippage=SlippageModel(
                slip_base=0.0,
                slip_k=0.0,
                spike_tr_atr_th=10.0,
                spike_mult=1.0,
            ),
            scenarios={"A": 1.0, "B": 1.0, "C": 1.0},
        ),
        validation=Validation(
            walk_forward=WalkForward(train=1, val=1, test=1),
            perturb_core_params_pct=0.0
        ),
        montecarlo=MonteCarlo(
            mc1=MonteCarlo1(block_min=1, block_max=1, n_sims=1),
            mc2=MonteCarlo2(spread_noise_range=(1.0, 1.0), slippage_noise_range=(1.0, 1.0), n_sims=1),
        ),
        outputs=Outputs(runs_dir="./runs", write_trades_csv=False, write_report_json=False, write_mc_json=False),
        reproducibility=Reproducibility(random_seed=42),
        regime=Regime(),
    )


class TestAtrPipsRegression:
    """Regression tests for atr_pips computation."""

    def test_atr_pips_computed_with_s2_strategy(self):
        """
        Verify that atr_pips is computed even when only S2 (which uses atr_short/atr_long) is enabled.
        This is a regression test for KeyError: 'atr' in _prepare_features.
        """
        config = _create_s2_only_config()
        df = _create_minimal_ohlc(num_bars=100)
        
        # Load strategies from config
        from backtest.orchestrator import _load_strategies
        strategies = _load_strategies(config)
        
        # Run _prepare_features
        prepared = _prepare_features({"EURGBP": df}, strategies, config)
        
        # Verify atr exists in prepared data
        assert "EURGBP" in prepared
        df_result = prepared["EURGBP"]
        
        # Key assertion: atr must exist (even though S2 only uses atr_short)
        assert "atr" in df_result.columns, "atr column should be created"
        
        # atr_pips must also exist
        assert "atr_pips" in df_result.columns, "atr_pips column should be created"
        
        # atr_pips should be valid (not all NaN)
        assert not df_result["atr_pips"].isna().all(), "atr_pips should have valid values"
        
        # atr_short should also exist (from S2 strategy)
        assert "atr_short" in df_result.columns, "atr_short should be created by S2 strategy"

    def test_atr_pips_with_multiple_strategies(self):
        """
        Verify atr_pips works with mixed strategies (some compute atr, some don't).
        """
        # Create config with S1_TREND_EMA_ATR_ADX (which computes atr)
        config = Config(
            universe=Universe(symbols=["EURUSD"], timeframe="M1"),
            bar_contract=BarContract(signal_on="close", fill_on="open_next", allow_bar0=False),
            strategies=Strategies(
                enabled=["S1_TREND_EMA_ATR_ADX"],
                params={
                    "S1_TREND_EMA_ATR_ADX": {
                        "ema_fast": 20,
                        "ema_slow": 50,
                        "atr_period": 14,
                        "adx_period": 14,
                        "k_sl": 3.0,
                    },
                    "S1_TREND_BREAKOUT_DONCHIAN": {},
                    "S1_TREND_BREAKOUT_RETEST": {},
                    "S2_MR_ZSCORE_EMA_REGIME": {},
                    "S2_TREND_EXPANSION_BREAKOUT": {},
                    "S3_BREAKOUT_ATR_REGIME_EMA200": {},
                }
            ),
            risk=Risk(
                r_base=1.0,
                caps=RiskCaps(per_strategy=100.0, per_symbol=100.0, usd_exposure_cap=1_000_000.0),
                conflict_policy="netting",
                priority_order=None,
                dd_day_limit=1.0,
                dd_week_limit=1.0,
                max_execution_errors=1,
            ),
            costs=Costs(
                spread_baseline_pips={"EURUSD": 0.0},
                slippage=SlippageModel(
                    slip_base=0.0,
                    slip_k=0.0,
                    spike_tr_atr_th=10.0,
                    spike_mult=1.0,
                ),
                scenarios={"A": 1.0, "B": 1.0, "C": 1.0},
            ),
            validation=Validation(walk_forward=WalkForward(train=1, val=1, test=1), perturb_core_params_pct=0.0),
            montecarlo=MonteCarlo(
                mc1=MonteCarlo1(block_min=1, block_max=1, n_sims=1),
                mc2=MonteCarlo2(spread_noise_range=(1.0, 1.0), slippage_noise_range=(1.0, 1.0), n_sims=1),
            ),
            outputs=Outputs(runs_dir="./runs", write_trades_csv=False, write_report_json=False, write_mc_json=False),
            reproducibility=Reproducibility(random_seed=42),
            regime=Regime(),
        )
        
        df = _create_minimal_ohlc(num_bars=100)
        
        from backtest.orchestrator import _load_strategies
        strategies = _load_strategies(config)
        prepared = _prepare_features({"EURUSD": df}, strategies, config)
        
        # Verify atr_pips computed successfully
        assert "EURUSD" in prepared
        df_result = prepared["EURUSD"]
        assert "atr" in df_result.columns
        assert "atr_pips" in df_result.columns
        assert not df_result["atr_pips"].isna().all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
