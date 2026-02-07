from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .backtester import BacktestResult, Backtester
from .strategy_template import Strategy


@dataclass(frozen=True)
class WalkForwardConfig:
    train_size: int
    test_size: int
    step_size: int | None = None


@dataclass
class WalkForwardResult:
    folds: list[dict]
    combined_equity: pd.Series


class WalkForwardRunner:
    def __init__(self, config: WalkForwardConfig) -> None:
        self.config = config

    def run(self, df: pd.DataFrame, strategy: Strategy, backtester: Backtester) -> WalkForwardResult:
        step = self.config.step_size or self.config.test_size
        folds: list[dict] = []
        equity_parts: list[pd.Series] = []

        for fold_id, (train_idx, test_idx) in enumerate(
            self._iter_windows(len(df), self.config.train_size, self.config.test_size, step)
        ):
            train_df = df.iloc[train_idx]
            test_df = df.iloc[test_idx]
            _ = train_df  # reserved for future fit/tune hooks

            result: BacktestResult = backtester.run(test_df, strategy)
            folds.append(
                {
                    "fold": fold_id,
                    "train_start": train_df.index[0],
                    "train_end": train_df.index[-1],
                    "test_start": test_df.index[0],
                    "test_end": test_df.index[-1],
                    "metrics": result.metrics,
                }
            )
            equity_parts.append(result.equity_curve)

        combined = pd.concat(equity_parts).sort_index() if equity_parts else pd.Series(dtype=float)
        return WalkForwardResult(folds=folds, combined_equity=combined)

    @staticmethod
    def _iter_windows(n: int, train: int, test: int, step: int):
        if min(n, train, test, step) <= 0:
            raise ValueError("n, train, test and step must be > 0")
        start = 0
        while start + train + test <= n:
            train_idx = range(start, start + train)
            test_idx = range(start + train, start + train + test)
            yield train_idx, test_idx
            start += step
