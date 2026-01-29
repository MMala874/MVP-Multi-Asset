from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Dict, Iterable, List, Sequence

import numpy as np
import pandas as pd

from validation.stress import apply_cost_stress
from validation.walk_forward import generate_splits


@dataclass(frozen=True)
class ScoreWeights:
    lambda_dd: float = 1.0
    mu_dd_duration: float = 0.1
    nu_cost_sensitivity: float = 0.1


class FilterTuner:
    def __init__(
        self,
        top_k: int = 5,
        weights: ScoreWeights | None = None,
        cost_stress_level: str = "B",
    ) -> None:
        self._top_k = top_k
        self._weights = weights or ScoreWeights()
        self._cost_stress_level = cost_stress_level

    def tune(
        self,
        strategy_id: str,
        base_config: object,
        df_by_symbol: Dict[str, pd.DataFrame],
    ) -> List[Dict[str, object]]:
        splits = generate_splits(_concat_index(df_by_symbol), base_config)
        if not splits:
            return []
        search_space = self._build_search_space(strategy_id)
        results: List[Dict[str, object]] = []
        for params in search_space:
            split_scores = []
            for train_idx, val_idx, _ in splits:
                score = self._score_split(strategy_id, params, base_config, df_by_symbol, train_idx, val_idx)
                split_scores.append(score)
            if not split_scores:
                continue
            robust_score = float(np.mean(split_scores) - np.std(split_scores))
            results.append({"params": params, "score": robust_score, "split_scores": split_scores})
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[: self._top_k]

    def _build_search_space(self, strategy_id: str) -> List[Dict[str, float]]:
        strategy_key = strategy_id.upper()
        if strategy_key == "S1_TREND_EMA_ATR_ADX":
            adx_th = [10.0, 15.0, 20.0, 25.0, 30.0]
            min_atr_pct = [0.1, 0.2, 0.3, 0.4]
            return [
                {"adx_th": a, "min_atr_pct": m}
                for a, m in product(adx_th, min_atr_pct)
            ]
        if strategy_key == "S2_MR_ZSCORE_EMA_REGIME":
            adx_max = [15.0, 20.0, 25.0, 30.0, 35.0]
            slope_th = [0.005, 0.01, 0.02, 0.03]
            return [
                {"adx_max": a, "slope_th": s}
                for a, s in product(adx_max, slope_th)
            ]
        if strategy_key == "S3_BREAKOUT_ATR_REGIME_EMA200":
            low = [0.2, 0.3, 0.4]
            high = [0.6, 0.7, 0.8]
            spike_block = [True, False]
            combos = []
            for l, h, s in product(low, high, spike_block):
                if h <= l:
                    continue
                combos.append(
                    {
                        "atr_pct_percentile_low": l,
                        "atr_pct_percentile_high": h,
                        "spike_block": s,
                    }
                )
            return combos
        raise ValueError(f"Unsupported strategy_id for tuning: {strategy_id}")

    def _score_split(
        self,
        strategy_id: str,
        params: Dict[str, float],
        base_config: object,
        df_by_symbol: Dict[str, pd.DataFrame],
        train_idx: Sequence[int],
        val_idx: Sequence[int],
    ) -> float:
        df = _concat_frames(df_by_symbol)
        filtered_val = _apply_filters(strategy_id, params, df, train_idx, val_idx)
        if filtered_val.empty:
            return -float("inf")
        pnl = filtered_val["pnl"].astype(float)
        expectancy = float(pnl.mean())
        max_dd = float(_max_drawdown(pnl))
        dd_duration = float(_max_drawdown_duration(pnl))
        cost_sensitivity = float(
            _cost_sensitivity(base_config, pnl, stress_level=self._cost_stress_level)
        )
        return self._score(expectancy, max_dd, dd_duration, cost_sensitivity)

    def _score(
        self,
        expectancy: float,
        max_dd: float,
        dd_duration: float,
        cost_sensitivity: float,
    ) -> float:
        penalty_dd = self._weights.lambda_dd * abs(max_dd)
        penalty_duration = self._weights.mu_dd_duration * dd_duration
        penalty_cost = self._weights.nu_cost_sensitivity * cost_sensitivity
        return expectancy - penalty_dd - penalty_duration - penalty_cost


def _concat_index(df_by_symbol: Dict[str, pd.DataFrame]) -> pd.Index:
    if not df_by_symbol:
        return pd.Index([])
    return next(iter(df_by_symbol.values())).index


def _concat_frames(df_by_symbol: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    if not df_by_symbol:
        return pd.DataFrame()
    frames = []
    for symbol, df in df_by_symbol.items():
        frame = df.copy()
        frame["symbol"] = symbol
        frames.append(frame)
    return pd.concat(frames, axis=0)


def _apply_filters(
    strategy_id: str,
    params: Dict[str, float],
    df: pd.DataFrame,
    train_idx: Sequence[int],
    val_idx: Sequence[int],
) -> pd.DataFrame:
    strategy_key = strategy_id.upper()
    df_val = df.iloc[list(val_idx)]
    if strategy_key == "S1_TREND_EMA_ATR_ADX":
        mask = df_val["adx"] > float(params["adx_th"])
        mask &= df_val["atr_pct"] >= float(params["min_atr_pct"])
        return df_val.loc[mask]
    if strategy_key == "S2_MR_ZSCORE_EMA_REGIME":
        mask = df_val["adx"] < float(params["adx_max"])
        mask &= df_val["slope"].abs() < float(params["slope_th"])
        return df_val.loc[mask]
    if strategy_key == "S3_BREAKOUT_ATR_REGIME_EMA200":
        low = float(params["atr_pct_percentile_low"])
        high = float(params["atr_pct_percentile_high"])
        low_th, high_th = _train_quantile_thresholds(df, train_idx, "atr_pct", low, high)
        mask = (df_val["atr_pct"] >= low_th) & (df_val["atr_pct"] <= high_th)
        if params.get("spike_block"):
            if "spike" in df_val.columns:
                mask &= ~df_val["spike"].astype(bool)
        return df_val.loc[mask]
    raise ValueError(f"Unsupported strategy_id for tuning: {strategy_id}")


def _max_drawdown(pnl: pd.Series) -> float:
    cumulative = pnl.cumsum()
    drawdown = cumulative - cumulative.cummax()
    if drawdown.empty:
        return 0.0
    return float(drawdown.min())


def _train_quantile_thresholds(
    df: pd.DataFrame,
    train_idx: Sequence[int],
    column: str,
    low: float,
    high: float,
) -> tuple[float, float]:
    train = df.iloc[list(train_idx)]
    if train.empty:
        raise ValueError("Train segment is empty; cannot compute quantile thresholds.")
    return float(train[column].quantile(low)), float(train[column].quantile(high))


def _max_drawdown_duration(pnl: pd.Series) -> int:
    cumulative = pnl.cumsum()
    running_max = cumulative.cummax()
    in_drawdown = cumulative < running_max
    max_duration = 0
    current = 0
    for flag in in_drawdown:
        if flag:
            current += 1
            max_duration = max(max_duration, current)
        else:
            current = 0
    return max_duration


def _cost_sensitivity(base_config: object, pnl: pd.Series, stress_level: str) -> float:
    base_cost = _estimate_cost_per_trade(base_config)
    stressed = apply_cost_stress(base_config, stress_level)
    stressed_cost = _estimate_cost_per_trade(stressed)
    delta_cost = stressed_cost - base_cost
    stressed_expectancy = float((pnl - delta_cost).mean())
    return abs(float(pnl.mean()) - stressed_expectancy)


def _estimate_cost_per_trade(config: object) -> float:
    costs = _getattr(config, "costs")
    if costs is None:
        return 0.0
    spread = _getattr(costs, "spread_baseline_pips", {})
    spread_values = list(spread.values()) if isinstance(spread, dict) else []
    spread_mean = float(np.mean(spread_values)) if spread_values else 0.0
    slippage = _getattr(costs, "slippage")
    slip_base = float(_getattr(slippage, "slip_base", 0.0)) if slippage is not None else 0.0
    return spread_mean + slip_base


def _getattr(obj: object, name: str, default: object = None) -> object:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


__all__ = ["FilterTuner", "ScoreWeights"]
