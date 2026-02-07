from __future__ import annotations

import pandas as pd


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            (df["high"] - df["low"]),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n, min_periods=max(5, n // 2)).mean()


def _prev_day_levels(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    day = df.index.normalize()
    pdh = df["high"].resample("1D").max().shift(1)
    pdl = df["low"].resample("1D").min().shift(1)
    return pd.Series(pdh.reindex(day).to_numpy(), index=df.index), pd.Series(pdl.reindex(day).to_numpy(), index=df.index)


def event_prev_day_sweep_reclaim(df: pd.DataFrame, reclaim_bars: int = 4) -> pd.Series:
    pdh, pdl = _prev_day_levels(df)
    sweep = (df["high"] > pdh) | (df["low"] < pdl)
    close_inside = (df["close"] <= pdh) & (df["close"] >= pdl)
    reclaim_soon = close_inside.rolling(reclaim_bars, min_periods=1).max().shift(-(reclaim_bars - 1)).fillna(0).astype(bool)
    return (sweep & reclaim_soon).rename("E_prev_day_sweep_reclaim")


def event_range_compression_break(df: pd.DataFrame, lookback: int = 64, q_low: float = 0.2, k_atr: float = 1.4, confirm_bars: int = 3) -> pd.Series:
    rng = df["high"] - df["low"]
    atr = _atr(df, 14)
    low_thr = rng.shift(1).rolling(lookback, min_periods=lookback // 2).quantile(q_low)
    compressed = rng <= low_thr
    expanded = rng > (k_atr * atr)
    expand_soon = expanded.rolling(confirm_bars, min_periods=1).max().shift(-(confirm_bars - 1)).fillna(0).astype(bool)
    return (compressed & expand_soon).rename("E_range_compression_break")


def event_impulse_pullback(df: pd.DataFrame, k_atr: float = 1.2, pullback_min: float = 0.25, pullback_max: float = 0.6, within_bars: int = 5) -> pd.Series:
    atr = _atr(df, 14)
    body = (df["close"] - df["open"]).abs()
    impulse = body > (k_atr * atr)
    roll_high = df["high"].rolling(20, min_periods=10).max()
    roll_low = df["low"].rolling(20, min_periods=10).min()
    pos = (df["close"] - roll_low) / (roll_high - roll_low).replace(0.0, pd.NA)
    pb = pos.between(pullback_min, pullback_max)
    pb_soon = pb.rolling(within_bars, min_periods=1).max().shift(-(within_bars - 1)).fillna(0).astype(bool)
    return (impulse & pb_soon).rename("E_impulse_pullback")


def event_liquidity_void_fill_proxy(df: pd.DataFrame, gap_k_atr: float = 1.6, fill_bars: int = 6, ema_span: int = 20) -> pd.Series:
    atr = _atr(df, 14)
    prev_close = df["close"].shift(1)
    gap = (df["open"] - prev_close).abs()
    void = gap > (gap_k_atr * atr)
    ema = df["close"].ewm(span=ema_span, adjust=False).mean()
    near_mean = ((df["close"] - ema).abs() <= 0.3 * atr)
    fill_soon = near_mean.rolling(fill_bars, min_periods=1).max().shift(-(fill_bars - 1)).fillna(0).astype(bool)
    return (void & fill_soon).rename("E_liquidity_void_fill_proxy")


def build_event_matrix(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    cfg = config or {}
    out = pd.DataFrame(index=df.index)
    out["E_prev_day_sweep_reclaim"] = event_prev_day_sweep_reclaim(df, reclaim_bars=int(cfg.get("reclaim_bars", 4)))
    out["E_range_compression_break"] = event_range_compression_break(
        df,
        lookback=int(cfg.get("compression_lookback", 64)),
        q_low=float(cfg.get("compression_q", 0.2)),
        k_atr=float(cfg.get("compression_k_atr", 1.4)),
        confirm_bars=int(cfg.get("compression_confirm", 3)),
    )
    out["E_impulse_pullback"] = event_impulse_pullback(
        df,
        k_atr=float(cfg.get("impulse_k_atr", 1.2)),
        pullback_min=float(cfg.get("pullback_min", 0.25)),
        pullback_max=float(cfg.get("pullback_max", 0.6)),
        within_bars=int(cfg.get("pullback_within", 5)),
    )
    out["E_liquidity_void_fill_proxy"] = event_liquidity_void_fill_proxy(
        df,
        gap_k_atr=float(cfg.get("void_gap_k_atr", 1.6)),
        fill_bars=int(cfg.get("void_fill_bars", 6)),
        ema_span=int(cfg.get("void_ema_span", 20)),
    )
    out["event_mask"] = out.any(axis=1)
    return out
