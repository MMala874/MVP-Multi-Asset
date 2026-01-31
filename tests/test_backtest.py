import pandas as pd
import pytest

from backtest.metrics import compute_metrics
from backtest.orchestrator import BacktestOrchestrator
from backtest.trade_log import TRADE_LOG_COLUMNS
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


@pytest.fixture
def df_eurusd_1min_1000():
    """Create a 1000-bar EURUSD M1 fixture for testing."""
    import numpy as np
    n_bars = 1000
    np.random.seed(42)
    returns = np.random.randn(n_bars) * 0.001
    close = (1 + returns).cumprod()
    return pd.DataFrame({
        "open": close * (1 + np.random.randn(n_bars) * 0.0001),
        "high": close * (1 + np.abs(np.random.randn(n_bars) * 0.0003)),
        "low": close * (1 - np.abs(np.random.randn(n_bars) * 0.0003)),
        "close": close,
    })


def _make_config() -> Config:
    return Config(
        universe=Universe(symbols=["EURUSD"], timeframe="M1"),
        bar_contract=BarContract(signal_on="close", fill_on="open_next", allow_bar0=False),
        strategies=Strategies(
            enabled=["S1_TREND_EMA_ATR_ADX"],
            params={
                "S1_TREND_EMA_ATR_ADX": {
                    "ema_fast": 1,
                    "ema_slow": 2,
                    "atr_period": 1,
                    "adx_period": 1,
                    "k_sl": 1.0,
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
        reproducibility=Reproducibility(random_seed=1),
    )


def _make_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [1.0, 1.1, 1.2, 1.3],
            "high": [1.05, 1.15, 1.25, 1.35],
            "low": [0.95, 1.05, 1.15, 1.25],
            "close": [1.0, 1.1, 1.2, 1.3],
        }
    )


def test_bar_contract_enforced():
    orchestrator = BacktestOrchestrator()
    config = _make_config()
    df = _make_df()

    trades, _ = orchestrator.run({"EURUSD": df}, config)
    scenario_a = trades[trades["scenario"] == "A"]
    assert not scenario_a.empty

    for _, row in scenario_a.iterrows():
        expected = df["open"].iat[int(row["signal_idx"]) + 1]
        assert row["entry_price"] == expected


def test_outputs_have_required_columns():
    orchestrator = BacktestOrchestrator()
    config = _make_config()
    df = _make_df()

    trades, _ = orchestrator.run({"EURUSD": df}, config)
    for column in TRADE_LOG_COLUMNS:
        assert column in trades.columns


def test_scenarios_three_runs():
    orchestrator = BacktestOrchestrator()
    config = _make_config()
    df = _make_df()

    trades, _ = orchestrator.run({"EURUSD": df}, config)
    assert set(trades["scenario"].unique()) == {"A", "B", "C"}

def test_metrics_use_pnl_pips_when_available():
    """Verify metrics use pnl_pips when available, not pnl."""
    trades_df = pd.DataFrame({
        "pnl": [100.0, -50.0, 75.0],
        "pnl_pips": [10.0, -5.0, 7.5],
        "strategy_id": ["S1", "S1", "S1"],
        "symbol": ["EURUSD", "EURUSD", "EURUSD"],
        "regime_snapshot": ["A", "A", "A"],
        "scenario": ["A", "A", "A"],
    })
    
    metrics = compute_metrics(trades_df)
    overall = metrics["overall"]
    
    # Expectancy should be based on pnl_pips (10 - 5 + 7.5) / 3 = 4.166...
    expected_expectancy = (10.0 - 5.0 + 7.5) / 3
    assert abs(overall["expectancy"] - expected_expectancy) < 0.01, \
        f"Expected expectancy {expected_expectancy}, got {overall['expectancy']}"
    
    # Profit factor should be based on pnl_pips: (10 + 7.5) / abs(-5) = 3.5
    expected_profit_factor = (10.0 + 7.5) / abs(-5.0)
    assert abs(overall["profit_factor"] - expected_profit_factor) < 0.01, \
        f"Expected PF {expected_profit_factor}, got {overall['profit_factor']}"
    
    # Max drawdown computed from pnl_pips cumsum: [10, 5, 12.5]
    # Cummax: [10, 10, 12.5]
    # Drawdown: [0, -5, 0]
    # Min: -5.0
    expected_max_dd = -5.0
    assert abs(overall["max_drawdown"] - expected_max_dd) < 0.01, \
        f"Expected max_dd {expected_max_dd}, got {overall['max_drawdown']}"


def test_metrics_fallback_to_pnl_without_pnl_pips():
    """Verify metrics fallback to pnl when pnl_pips is not available."""
    trades_df = pd.DataFrame({
        "pnl": [10.0, -5.0, 7.5],
        "strategy_id": ["S1", "S1", "S1"],
        "symbol": ["EURUSD", "EURUSD", "EURUSD"],
        "regime_snapshot": ["A", "A", "A"],
        "scenario": ["A", "A", "A"],
    })
    
    metrics = compute_metrics(trades_df)
    overall = metrics["overall"]
    
    # Expectancy should be based on pnl (10 - 5 + 7.5) / 3 = 4.166...
    expected_expectancy = (10.0 - 5.0 + 7.5) / 3
    assert abs(overall["expectancy"] - expected_expectancy) < 0.01, \
        f"Expected expectancy {expected_expectancy}, got {overall['expectancy']}"
    
    # Profit factor: (10 + 7.5) / abs(-5) = 3.5
    expected_profit_factor = (10.0 + 7.5) / abs(-5.0)
    assert abs(overall["profit_factor"] - expected_profit_factor) < 0.01, \
        f"Expected PF {expected_profit_factor}, got {overall['profit_factor']}"


def test_orchestrator_scenario_filtering(df_eurusd_1min_1000):
    """Test that orchestrator can filter scenarios (e.g., run only B)."""
    config = _make_config()
    orchestrator = BacktestOrchestrator()
    
    # Run with scenarios=["B"] only
    trades, report = orchestrator.run({"EURUSD": df_eurusd_1min_1000}, config, scenarios=["B"])
    
    # Should have trades and report
    assert len(trades) > 0, "No trades generated for scenario B"
    assert "metrics" in report, "Report missing metrics"
    
    by_scenario = report["metrics"]["by_scenario"]
    
    # Only B scenario should be present
    assert "B" in by_scenario, "Scenario B missing from metrics"
    assert len(by_scenario) == 1, f"Expected only 1 scenario, got {len(by_scenario)}"
    
    # All trades should be from scenario B
    assert (trades["scenario"] == "B").all(), "Some trades are not from scenario B"


def test_orchestrator_all_scenarios_default(df_eurusd_1min_1000):
    """Test that orchestrator runs all scenarios by default (scenarios=None)."""
    config = _make_config()
    orchestrator = BacktestOrchestrator()
    
    # Run with scenarios=None (default)
    trades, report = orchestrator.run({"EURUSD": df_eurusd_1min_1000}, config, scenarios=None)
    
    # Should have all three scenarios
    by_scenario = report["metrics"]["by_scenario"]
    
    assert "A" in by_scenario, "Scenario A missing"
    assert "B" in by_scenario, "Scenario B missing"
    assert "C" in by_scenario, "Scenario C missing"
    assert len(by_scenario) == 3, f"Expected 3 scenarios, got {len(by_scenario)}"


def test_orchestrator_multiple_scenarios(df_eurusd_1min_1000):
    """Test that orchestrator can run specific scenario combinations."""
    config = _make_config()
    orchestrator = BacktestOrchestrator()
    
    # Run with scenarios=["A", "C"] (skip B)
    trades, report = orchestrator.run({"EURUSD": df_eurusd_1min_1000}, config, scenarios=["A", "C"])
    
    # Should have only A and C
    by_scenario = report["metrics"]["by_scenario"]
    
    assert "A" in by_scenario, "Scenario A missing"
    assert "C" in by_scenario, "Scenario C missing"
    assert "B" not in by_scenario, "Scenario B should not be present"
    assert len(by_scenario) == 2, f"Expected 2 scenarios, got {len(by_scenario)}"