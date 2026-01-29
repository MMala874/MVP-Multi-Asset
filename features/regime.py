import numpy as np
import pandas as pd

from .indicators import atr


def compute_atr_pct(df: pd.DataFrame, atr_n: int) -> pd.Series:
    atr_values = atr(df, atr_n)
    return atr_values / df["close"] * 100


def rolling_percentile(series: pd.Series, window: int, q: float) -> pd.Series:
    def _percentile(values: np.ndarray) -> float:
        return float(np.percentile(values, q))

    return series.rolling(window=window, min_periods=window).apply(
        _percentile, raw=True
    )


def classify_vol_regime(
    atr_pct: pd.Series | float, p35: float, p75: float
) -> pd.Series | str:
    def _classify(value: float) -> str:
        if value < p35:
            return "LOW"
        if value < p75:
            return "MID"
        return "HIGH"

    if isinstance(atr_pct, pd.Series):
        return atr_pct.apply(_classify)
    return _classify(float(atr_pct))


def spike_flag(tr_atr: pd.Series | float, th: float = 2.5) -> pd.Series | bool:
    if isinstance(tr_atr, pd.Series):
        return tr_atr > th
    return float(tr_atr) > th
