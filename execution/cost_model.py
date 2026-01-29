from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ScenarioAdjustments:
    spread_mult: float
    slippage_mult: float
    slippage_add: float
    apply_spike: bool


_SCENARIOS = {
    "A": ScenarioAdjustments(spread_mult=1.0, slippage_mult=1.0, slippage_add=0.0, apply_spike=False),
    "B": ScenarioAdjustments(spread_mult=1.3, slippage_mult=1.0, slippage_add=0.3, apply_spike=False),
    "C": ScenarioAdjustments(spread_mult=1.6, slippage_mult=1.8, slippage_add=0.0, apply_spike=True),
}


class CostModel:
    def __init__(self, config: object) -> None:
        self._config = config

    def spread_pips(self, symbol: str, scenario: str) -> float:
        adjustments = self._get_scenario(scenario)
        base_spread = self._config.costs.spread_baseline_pips[symbol]
        return base_spread * adjustments.spread_mult

    def slippage_pips(
        self,
        df: pd.DataFrame,
        idx_t: int,
        symbol: str,
        atr_series: pd.Series,
        scenario: str,
    ) -> float:
        adjustments = self._get_scenario(scenario)
        tr_next = self._true_range_next(df, idx_t)
        atr_t = float(atr_series.iat[idx_t])
        slip_cfg = self._config.costs.slippage
        slippage = slip_cfg.slip_base + slip_cfg.slip_k * (tr_next / atr_t)
        if adjustments.apply_spike:
            if (tr_next / atr_t) > slip_cfg.spike_tr_atr_th:
                slippage *= slip_cfg.spike_mult
        slippage = slippage * adjustments.slippage_mult + adjustments.slippage_add
        return float(slippage)

    def trade_cost_pips(
        self,
        symbol: str,
        idx_t: int,
        scenario: str,
        df: pd.DataFrame,
        atr_series: pd.Series,
    ) -> tuple[float, float]:
        spread = self.spread_pips(symbol, scenario)
        slippage = self.slippage_pips(df, idx_t, symbol, atr_series, scenario)
        per_side = (spread / 2.0) + slippage
        return per_side, per_side

    def _get_scenario(self, scenario: str) -> ScenarioAdjustments:
        if scenario not in _SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario}")
        return _SCENARIOS[scenario]

    @staticmethod
    def _true_range_next(df: pd.DataFrame, idx_t: int) -> float:
        idx_next = idx_t + 1
        if idx_next >= len(df):
            raise IndexError("idx_t+1 out of range for true range calculation")
        high_next = float(df["high"].iat[idx_next])
        low_next = float(df["low"].iat[idx_next])
        prev_close = float(df["close"].iat[idx_t])
        ranges = [
            high_next - low_next,
            abs(high_next - prev_close),
            abs(low_next - prev_close),
        ]
        return max(ranges)
