from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .backtester import BacktestConfig, Backtester
from .strategy_template import Strategy


@dataclass(frozen=True)
class StressScenario:
    name: str
    commission_mult: float = 1.0
    slippage_mult: float = 1.0
    atr_shock_mult: float = 1.0


class StressTestRunner:
    def __init__(self, scenarios: list[StressScenario]) -> None:
        self.scenarios = scenarios

    def run(
        self,
        df: pd.DataFrame,
        strategy: Strategy,
        base_config: BacktestConfig,
    ) -> pd.DataFrame:
        rows = []
        for scn in self.scenarios:
            cfg = BacktestConfig(
                commission_per_contract=base_config.commission_per_contract * scn.commission_mult,
                slippage_base=base_config.slippage_base * scn.slippage_mult,
                slippage_vol_coeff=base_config.slippage_vol_coeff * scn.slippage_mult,
                initial_capital=base_config.initial_capital,
            )
            stressed = df.copy()
            stressed["atr"] = stressed["atr"] * scn.atr_shock_mult

            result = Backtester(cfg).run(stressed, strategy)
            rows.append({"scenario": scn.name, **result.metrics})
        return pd.DataFrame(rows)
