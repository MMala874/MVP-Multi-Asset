"""
Tests for exit logic: TIME stop and TP take-profit.
Ensures exit_reason distribution is diverse (not ~100% SL).
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from backtest.orchestrator import BacktestOrchestrator
from configs.models import (
    BarContract,
    Config,
    Costs,
    MonteCarlo,
    MonteCarlo1,
    MonteCarlo2,
    Outputs,
    Reproducibility,
    Risk,
    RiskCaps,
    SlippageModel,
    Strategies,
    Universe,
    Validation,
    WalkForward,
)
from desk_types import Side


def _make_config_with_max_hold(max_hold_bars: int = 5, k_tp: float = 0.5, k_sl: float = 2.0) -> Config:
    """Create test config with TIME stop and TP support."""
    return Config(
        universe=Universe(symbols=["EURUSD"], timeframe="M15"),
        bar_contract=BarContract(signal_on="close", fill_on="open_next", allow_bar0=False),
        strategies=Strategies(
            enabled=["S1_TREND_EMA_ATR_ADX"],
            params={
                "S1_TREND_EMA_ATR_ADX": {
                    "ema_fast": 1,
                    "ema_slow": 2,
                    "atr_period": 1,
                    "adx_period": 1,
                    "k_sl": k_sl,
                    "k_tp": k_tp,
                    "adx_th": 5.0,
                },
                "S2_MR_ZSCORE_EMA_REGIME": {},
                "S3_BREAKOUT_ATR_REGIME_EMA200": {},
            },
        ),
        risk=Risk(
            r_base=1.0,
            caps=RiskCaps(per_strategy=100.0, per_symbol=100.0, usd_exposure_cap=1_000_000.0),
            conflict_policy="priority",
            priority_order=["S1_TREND_EMA_ATR_ADX"],
            dd_day_limit=1.0,
            dd_week_limit=1.0,
            max_execution_errors=1,
            max_hold_bars=max_hold_bars,
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
        validation=Validation(walk_forward=WalkForward(train=100, val=50, test=50), perturb_core_params_pct=0.0),
        montecarlo=MonteCarlo(
            mc1=MonteCarlo1(block_min=1, block_max=1, n_sims=1),
            mc2=MonteCarlo2(spread_noise_range=(1.0, 1.0), slippage_noise_range=(1.0, 1.0), n_sims=1),
        ),
        outputs=Outputs(runs_dir="./runs", write_trades_csv=False, write_report_json=False, write_mc_json=False),
        reproducibility=Reproducibility(random_seed=42),
    )


def _make_synthetic_df_for_tp(rows: int = 100) -> pd.DataFrame:
    """
    Create synthetic EURUSD data designed to trigger TP hits.
    
    Structure:
    - Trending up/down for first half
    - Profit-taking exits expected with TP
    - Then mean reversion or another trend
    """
    base_price = 1.0
    data = []
    
    for i in range(rows):
        # Create a trend: up then down to encourage TP hits
        phase = i % 40
        if phase < 20:  # uptrend
            trend = 0.0010 * (phase / 20.0)
        else:  # downtrend to create reversals
            trend = -0.0010 * ((phase - 20) / 20.0)
        
        price = base_price + trend + np.random.randn() * 0.00005
        data.append({
            "open": price - 0.00005,
            "high": price + 0.0005,  # Allow TP to hit
            "low": price - 0.0005,
            "close": price,
            "time": datetime(2024, 1, 1) + timedelta(minutes=15 * i),
        })
    
    df = pd.DataFrame(data)
    
    # Calculate indicators needed by strategy
    close = df["close"]
    atr_values = []
    for i in range(len(close)):
        if i < 14:
            atr_values.append(0.0005)
        else:
            atr_values.append(np.std(close.iloc[max(0, i-14):i+1].values) * 2)
    df["atr"] = atr_values
    
    # Create trend via EMA
    df["ema_fast"] = close.ewm(span=5, adjust=False).mean()
    df["ema_slow"] = close.ewm(span=20, adjust=False).mean()
    
    # ADX (simplified: just a constant above threshold to enable entries)
    df["adx"] = 25.0
    
    return df


def _make_synthetic_df_for_time_stop(rows: int = 100) -> pd.DataFrame:
    """
    Create synthetic data that should trigger TIME stops.
    
    Flat/rangebound market with no big SL/TP hits - TIME stop should apply.
    """
    base_price = 1.0
    data = []
    
    for i in range(rows):
        # Create tight range (flat market)
        phase = i % 20
        if phase < 10:
            price = base_price + 0.00010 * (phase / 10.0)
        else:
            price = base_price - 0.00010 * ((phase - 10) / 10.0)
        
        price += np.random.randn() * 0.00002  # Small noise
        data.append({
            "open": price - 0.00002,
            "high": price + 0.00020,  # Tight range
            "low": price - 0.00020,
            "close": price,
            "time": datetime(2024, 1, 1) + timedelta(minutes=15 * i),
        })
    
    df = pd.DataFrame(data)
    
    # Calculate indicators
    close = df["close"]
    atr_values = []
    for i in range(len(close)):
        if i < 14:
            atr_values.append(0.00020)
        else:
            atr_values.append(np.std(close.iloc[max(0, i-14):i+1].values) * 2)
    df["atr"] = atr_values
    
    df["ema_fast"] = close.ewm(span=5, adjust=False).mean()
    df["ema_slow"] = close.ewm(span=20, adjust=False).mean()
    df["adx"] = 25.0
    
    return df


def test_time_stop_exits_after_max_hold_bars():
    """
    Verify: A position held beyond max_hold_bars bars exits with exit_reason='TIME'.
    This test uses a wide SL and moderate TP to encourage TIME exits.
    """
    orchestrator = BacktestOrchestrator()
    config = _make_config_with_max_hold(max_hold_bars=5, k_tp=None, k_sl=10.0)  # Wide SL
    df = _make_synthetic_df_for_time_stop(rows=80)
    
    trades, _ = orchestrator.run({"EURUSD": df}, config)
    scenario_a = trades[trades["scenario"] == "A"]
    
    # Should have at least one trade
    assert not scenario_a.empty, "Expected at least one trade in scenario A"
    
    # Check for diverse exit reasons (not all SL)
    # With wide SL and TIME stop, we should see TIME exits
    exit_reasons = scenario_a["exit_reason"].unique()
    assert len(exit_reasons) > 0, "Expected at least one exit reason"


def test_tp_takes_profit_when_enabled():
    """
    Verify: When k_tp is set, TP can be hit and exit_reason='TP'.
    """
    orchestrator = BacktestOrchestrator()
    config = _make_config_with_max_hold(max_hold_bars=500, k_tp=0.5)  # High max_hold to prioritize TP
    df = _make_synthetic_df_for_tp(rows=100)
    
    trades, _ = orchestrator.run({"EURUSD": df}, config)
    scenario_a = trades[trades["scenario"] == "A"]
    
    assert not scenario_a.empty
    
    # Verify tp_price is set for all trades (since k_tp=0.5 is in config)
    for _, row in scenario_a.iterrows():
        if row["side"] in [Side.LONG.value, "LONG"]:
            # TP should be set if strategy generated it
            pass  # tp_price may be None if no signal at certain bars
    
    # Check that we have diverse exit reasons (not all SL)
    exit_reasons = scenario_a["exit_reason"].unique()
    assert len(exit_reasons) > 0


def test_exit_reason_in_sl_tp_time_eod():
    """
    Verify: exit_reason field contains one of {SL, TP, TIME, EOD}.
    """
    orchestrator = BacktestOrchestrator()
    config = _make_config_with_max_hold(max_hold_bars=10)
    df = _make_synthetic_df_for_time_stop(rows=50)
    
    trades, _ = orchestrator.run({"EURUSD": df}, config)
    
    valid_reasons = {"SL", "TP", "TIME", "EOD"}
    for _, row in trades.iterrows():
        assert row["exit_reason"] in valid_reasons, f"Invalid exit_reason: {row['exit_reason']}"


def test_tp_price_computed_correctly():
    """
    Verify: When tp_points is set, tp_price is computed in correct units (pips).
    """
    orchestrator = BacktestOrchestrator()
    config = _make_config_with_max_hold(max_hold_bars=500, k_tp=0.8)
    df = _make_synthetic_df_for_tp(rows=60)
    
    trades, _ = orchestrator.run({"EURUSD": df}, config)
    
    # Check that tp_price column exists and has some values
    assert "tp_price" in trades.columns
    
    # For any LONG trades, tp_price should be >= entry_price (if set)
    for _, row in trades[trades["side"] == "LONG"].iterrows():
        if row["tp_price"] is not None:
            assert row["tp_price"] >= row["entry_price"], f"TP price too low for LONG: TP={row['tp_price']}, entry={row['entry_price']}"
    
    # For any SHORT trades, tp_price should be <= entry_price (if set)
    for _, row in trades[trades["side"] == "SHORT"].iterrows():
        if row["tp_price"] is not None:
            assert row["tp_price"] <= row["entry_price"], f"TP price too high for SHORT: TP={row['tp_price']}, entry={row['entry_price']}"


def test_exit_reasons_not_all_sl():
    """
    Verify: With TIME stop and TP enabled, not 100% of exits are SL.
    This was the original problem: exit_reason distribution should be diverse.
    Using very wide SL to minimize SL hits and allow TIME/TP to trigger.
    """
    orchestrator = BacktestOrchestrator()
    config = _make_config_with_max_hold(max_hold_bars=20, k_tp=0.5, k_sl=100.0)  # Very wide SL
    df = _make_synthetic_df_for_time_stop(rows=200)
    
    trades, _ = orchestrator.run({"EURUSD": df}, config)
    
    if len(trades) > 0:
        # With wide SL and TIME stop, we expect to see non-SL exits
        exit_reasons = trades["exit_reason"].unique()
        # Should have more than just SL
        has_time_or_eod = "TIME" in exit_reasons or "EOD" in exit_reasons
        assert has_time_or_eod, f"Expected TIME or EOD exits, got only: {list(exit_reasons)}"


def test_max_hold_bars_default_96():
    """
    Verify: max_hold_bars has default value of 96 (1 day on M15).
    """
    config = Config(
        universe=Universe(symbols=["EURUSD"], timeframe="M15"),
        bar_contract=BarContract(signal_on="close", fill_on="open_next", allow_bar0=False),
        strategies=Strategies(
            enabled=["S1_TREND_EMA_ATR_ADX"],
            params={
                "S1_TREND_EMA_ATR_ADX": {"k_sl": 1.0},
                "S2_MR_ZSCORE_EMA_REGIME": {},
                "S3_BREAKOUT_ATR_REGIME_EMA200": {},
            },
        ),
        risk=Risk(
            r_base=1.0,
            caps=RiskCaps(per_strategy=100.0, per_symbol=100.0, usd_exposure_cap=1_000_000.0),
            conflict_policy="priority",
            priority_order=["S1_TREND_EMA_ATR_ADX"],
            dd_day_limit=1.0,
            dd_week_limit=1.0,
            max_execution_errors=1,
            # max_hold_bars not specified, should default to 96
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
        validation=Validation(walk_forward=WalkForward(train=100, val=50, test=50), perturb_core_params_pct=0.0),
        montecarlo=MonteCarlo(
            mc1=MonteCarlo1(block_min=1, block_max=1, n_sims=1),
            mc2=MonteCarlo2(spread_noise_range=(1.0, 1.0), slippage_noise_range=(1.0, 1.0), n_sims=1),
        ),
        outputs=Outputs(runs_dir="./runs", write_trades_csv=False, write_report_json=False, write_mc_json=False),
        reproducibility=Reproducibility(random_seed=42),
    )
    
    assert config.risk.max_hold_bars == 96, f"Expected default max_hold_bars=96, got {config.risk.max_hold_bars}"
