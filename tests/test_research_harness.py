from __future__ import annotations

import json

import pandas as pd

from src.research import (
    BacktestConfig,
    Backtester,
    Strategy,
    StressScenario,
    StressTestRunner,
    WalkForwardConfig,
    WalkForwardRunner,
    bootstrap_ci,
)


class DummyStrategy(Strategy):
    def generate_signal(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index)

    def risk_model(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=df.index)


def _sample_df(n: int = 40) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = pd.Series(100 + (pd.Series(range(n)) * 0.2), index=idx)
    atr = pd.Series(0.5, index=idx)
    return pd.DataFrame({"close": close, "atr": atr}, index=idx)


def test_backtester_costs_and_exports(tmp_path):
    df = _sample_df(12)
    strategy = DummyStrategy()
    bt = Backtester(BacktestConfig(commission_per_contract=0.1, slippage_base=0.01, slippage_vol_coeff=0.2))

    result = bt.run(df, strategy)
    bt.export(result, tmp_path)

    assert (tmp_path / "trades.csv").exists()
    assert (tmp_path / "metrics.json").exists()
    assert (tmp_path / "equity_curve.csv").exists()
    assert "max_drawdown" in result.metrics
    saved_metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert saved_metrics["n_bars"] == 12


def test_walkforward_automatic_and_stress_runner():
    df = _sample_df(50)
    strategy = DummyStrategy()
    cfg = BacktestConfig(commission_per_contract=0.05, slippage_base=0.01, slippage_vol_coeff=0.1)

    runner = WalkForwardRunner(WalkForwardConfig(train_size=20, test_size=10))
    wf = runner.run(df, strategy, Backtester(cfg))
    assert len(wf.folds) == 3
    assert not wf.combined_equity.empty

    stress = StressTestRunner(
        [
            StressScenario("base"),
            StressScenario("high_cost", commission_mult=2.0, slippage_mult=2.0, atr_shock_mult=1.5),
        ]
    )
    stress_df = stress.run(df, strategy, cfg)
    assert list(stress_df["scenario"]) == ["base", "high_cost"]
    assert "total_return" in stress_df.columns


def test_bootstrap_ci_reproducible():
    rets = pd.Series([0.01, -0.02, 0.015, 0.005, 0.0, 0.003])
    a = bootstrap_ci(rets, metric="mean", n_bootstrap=300, seed=7)
    b = bootstrap_ci(rets, metric="mean", n_bootstrap=300, seed=7)
    assert a == b
    assert a["ci_low"] <= a["point_estimate"] <= a["ci_high"]
