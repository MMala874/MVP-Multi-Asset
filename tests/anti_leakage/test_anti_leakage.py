import sys
from types import ModuleType

import numpy as np
import pandas as pd

from execution.fill_rules import get_fill_price
from features.indicators import atr, ema, slope, zscore
from features.regime import compute_atr_pct, rolling_percentile
from backtest.trade_log import TRADE_LOG_COLUMNS
from backtest.orchestrator import BacktestOrchestrator, _compute_regime
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
from desk_types import Side, SignalIntent
from validation.filter_tuner import _apply_filters


def test_feature_functions_ignore_future_data() -> None:
    series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    t = 5

    ema_original = ema(series, 3).iat[t]
    slope_original = slope(series, 3).iat[t]
    zscore_original = zscore(series, 3).iat[t]

    series_modified = series.copy()
    series_modified.iloc[t + 1 :] = series_modified.iloc[t + 1 :] + 100

    ema_modified = ema(series_modified, 3).iat[t]
    slope_modified = slope(series_modified, 3).iat[t]
    zscore_modified = zscore(series_modified, 3).iat[t]

    assert np.isclose(ema_original, ema_modified, equal_nan=True)
    assert np.isclose(slope_original, slope_modified, equal_nan=True)
    assert np.isclose(zscore_original, zscore_modified, equal_nan=True)

    df = pd.DataFrame(
        {
            "high": [10.0, 11.0, 12.0, 13.0],
            "low": [9.0, 10.0, 11.0, 12.0],
            "close": [9.5, 10.5, 11.5, 12.5],
        }
    )
    atr_original = atr(df, 2).iat[2]
    df_modified = df.copy()
    df_modified.loc[3, "high"] = 99.0
    df_modified.loc[3, "low"] = 1.0
    df_modified.loc[3, "close"] = 50.0
    atr_modified = atr(df_modified, 2).iat[2]
    assert np.isclose(atr_original, atr_modified, equal_nan=True)


def test_atr_pct_and_regime_ignore_future_data() -> None:
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

    atr_pct_original = compute_atr_pct(df, atr_n=atr_n).iat[t]
    regime_original = _compute_regime(df, window=window, atr_n=atr_n).iat[t]

    df_modified = df.copy()
    df_modified.loc[t + 1 :, "high"] = df_modified.loc[t + 1 :, "high"] + 50.0
    df_modified.loc[t + 1 :, "low"] = df_modified.loc[t + 1 :, "low"] - 50.0
    df_modified.loc[t + 1 :, "close"] = df_modified.loc[t + 1 :, "close"] + 25.0

    atr_pct_modified = compute_atr_pct(df_modified, atr_n=atr_n).iat[t]
    regime_modified = _compute_regime(df_modified, window=window, atr_n=atr_n).iat[t]

    assert np.isclose(atr_pct_original, atr_pct_modified, equal_nan=True)
    assert regime_original == regime_modified


def test_bar_contract_fill_is_open_next() -> None:
    df = pd.DataFrame({"open": [1.1, 1.2, 1.3]})
    assert get_fill_price(df, idx_t=0, side="buy") == 1.2


def test_rolling_percentile_uses_rolling_window() -> None:
    series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    window = 5
    t = 4

    original = rolling_percentile(series, window, 50).iat[t]

    modified = series.copy()
    modified.iloc[t + 1 :] = modified.iloc[t + 1 :] + 100

    recomputed = rolling_percentile(modified, window, 50).iat[t]
    assert np.isclose(original, recomputed, equal_nan=True)


def test_breakout_filter_uses_train_only_percentiles() -> None:
    df = pd.DataFrame(
        {
            "atr_pct": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            "pnl": [0.1] * 8,
        }
    )
    train_idx = range(0, 4)
    val_idx = range(4, 6)
    params = {"atr_pct_percentile_low": 0.2, "atr_pct_percentile_high": 0.8, "spike_block": False}

    baseline = _apply_filters("S3_BREAKOUT_ATR_REGIME_EMA200", params, df, train_idx, val_idx)

    df_modified = df.copy()
    df_modified.loc[list(val_idx), "atr_pct"] = [500.0, 600.0]

    recomputed = _apply_filters("S3_BREAKOUT_ATR_REGIME_EMA200", params, df_modified, train_idx, val_idx)

    assert baseline["atr_pct"].tolist() == recomputed["atr_pct"].tolist()


def test_trade_log_tracks_feature_time_bounds() -> None:
    assert "features_max_time_used" in TRADE_LOG_COLUMNS

    trade_log = pd.DataFrame(
        [
            {
                "trade_id": 1,
                "order_id": "o-1",
                "symbol": "EURUSD",
                "strategy_id": "s1",
                "side": "long",
                "qty": 1.0,
                "signal_time": pd.Timestamp("2024-01-01T00:00:00Z"),
                "signal_idx": 0,
                "fill_time": pd.Timestamp("2024-01-01T00:05:00Z"),
                "entry_price": 1.0,
                "exit_time": pd.Timestamp("2024-01-01T00:10:00Z"),
                "exit_price": 1.1,
                "pnl": 0.1,
                "pnl_pct": 0.1,
                "spread_used": 0.0,
                "slippage_used": 0.0,
                "scenario": "A",
                "regime_snapshot": "LOW",
                "reason_codes": "",
                "features_max_time_used": pd.Timestamp("2024-01-01T00:00:00Z"),
            }
        ]
    )

    assert (trade_log["features_max_time_used"] <= trade_log["signal_time"]).all()


def _make_dummy_config() -> Config:
    return Config(
        universe=Universe(symbols=["EURUSD"], timeframe="M1"),
        bar_contract=BarContract(signal_on="close", fill_on="open_next", allow_bar0=False),
        strategies=Strategies(
            enabled=["DUMMY_ANTI_LEAK"],
            params={"DUMMY_ANTI_LEAK": {}},
        ),
        risk=Risk(
            r_base=1.0,
            caps=RiskCaps(per_strategy=100.0, per_symbol=100.0, usd_exposure_cap=1_000_000.0),
            conflict_policy="priority",
            priority_order=["DUMMY_ANTI_LEAK"],
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


def _make_price_df(n_bars: int) -> pd.DataFrame:
    close = pd.Series(range(n_bars), dtype=float)
    return pd.DataFrame(
        {
            "open": close + 0.01,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
        }
    )


def test_orchestrator_strategies_do_not_see_future(monkeypatch) -> None:
    module = ModuleType("dummy_strategy")
    module.captured = []

    def generate_signal(ctx):
        df = ctx["df"]
        last_close = float(df["close"].iloc[-1])
        side = Side.LONG if last_close > 100 else Side.SHORT
        signal = SignalIntent(
            strategy_id="dummy",
            symbol=ctx["symbol"],
            side=side,
            signal_time=ctx["current_time"],
            sl_points=1.0,
            tp_points=None,
            tags={"last_close": f"{last_close:.2f}"},
        )
        if ctx["idx"] == 50:
            module.captured.append(signal)
        return signal

    module.generate_signal = generate_signal
    monkeypatch.setitem(sys.modules, "dummy_strategy", module)

    from backtest import orchestrator as orchestrator_module

    monkeypatch.setattr(
        orchestrator_module,
        "STRATEGY_MAP",
        {**orchestrator_module.STRATEGY_MAP, "DUMMY_ANTI_LEAK": "dummy_strategy"},
    )

    orchestrator = BacktestOrchestrator()
    config = _make_dummy_config()

    df = _make_price_df(100)
    module.captured = []
    orchestrator.run({"EURUSD": df}, config)
    assert module.captured
    baseline = module.captured[0].to_dict()

    df_modified = df.copy()
    df_modified.loc[80:, ["open", "high", "low", "close"]] += 200.0
    module.captured = []
    orchestrator.run({"EURUSD": df_modified}, config)
    assert module.captured
    modified = module.captured[0].to_dict()

    assert baseline == modified
