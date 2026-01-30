import inspect

import pandas as pd

from backtest.orchestrator import BacktestOrchestrator, _compute_regime
from configs.models import (
    BarContract,
    Config,
    Costs,
    MonteCarlo,
    MonteCarlo1,
    MonteCarlo2,
    Outputs,
    Regime,
    Reproducibility,
    Risk,
    RiskCaps,
    SlippageModel,
    Strategies,
    Universe,
    Validation,
    WalkForward,
)
import backtest.orchestrator as orchestrator_module


def test_no_lookahead_regime() -> None:
    df = pd.DataFrame(
        {
            "open": [10.0, 10.2, 10.4, 10.3, 10.6, 10.8, 11.0, 11.1],
            "high": [10.5, 10.6, 10.8, 10.7, 11.0, 11.2, 11.4, 11.5],
            "low": [9.8, 10.0, 10.2, 10.1, 10.4, 10.6, 10.8, 10.9],
            "close": [10.1, 10.3, 10.5, 10.4, 10.7, 10.9, 11.1, 11.2],
        }
    )
    t = 5
    atr_n = 3
    window = 3

    regime_original = _compute_regime(df, window=window, atr_n=atr_n).iat[t]

    df_modified = df.copy()
    df_modified.loc[t + 1 :, "high"] = df_modified.loc[t + 1 :, "high"] + 50.0
    df_modified.loc[t + 1 :, "low"] = df_modified.loc[t + 1 :, "low"] - 50.0
    df_modified.loc[t + 1 :, "close"] = df_modified.loc[t + 1 :, "close"] + 25.0

    regime_modified = _compute_regime(df_modified, window=window, atr_n=atr_n).iat[t]

    assert regime_original == regime_modified


def test_no_percentile_called() -> None:
    source = inspect.getsource(orchestrator_module)
    assert "rolling_percentile" not in source


def _make_config() -> Config:
    return Config(
        universe=Universe(symbols=["EURUSD"], timeframe="M1"),
        bar_contract=BarContract(signal_on="close", fill_on="open_next", allow_bar0=False),
        regime=Regime(atr_pct_window=2, atr_pct_n=2, z_low=-0.5, z_high=0.5, spike_tr_atr_th=2.5),
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
            "open": [1.0, 1.1, 1.2, 1.3, 1.4, 1.5],
            "high": [1.05, 1.15, 1.25, 1.35, 1.45, 1.55],
            "low": [0.95, 1.05, 1.15, 1.25, 1.35, 1.45],
            "close": [1.0, 1.1, 1.2, 1.3, 1.4, 1.5],
        }
    )


def test_backtest_runs_small() -> None:
    orchestrator = BacktestOrchestrator()
    config = _make_config()
    df = _make_df()

    trades, _ = orchestrator.run({"EURUSD": df}, config)
    assert not trades.empty
    assert trades["regime_snapshot"].notna().all()
    assert trades["regime_snapshot"].str.contains("VOL=").all()
