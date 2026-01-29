import pandas as pd

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
