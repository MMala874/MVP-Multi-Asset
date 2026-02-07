from __future__ import annotations

import pandas as pd

from edge_discovery.time_utils import ensure_datetime_index


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


def event_prev_day_sweep_reclaim(df: pd.DataFrame, reclaim_bars: int = 5) -> pd.Series:
    df = ensure_datetime_index(df)
    lookback = max(int(reclaim_bars), 1)
    pdh, pdl = _prev_day_levels(df)
    sweep_up = df["high"] > pdh
    sweep_dn = df["low"] < pdl
    reclaim = (df["close"] <= pdh) & (df["close"] >= pdl)
    recent_sweep = (sweep_up | sweep_dn).shift(1).rolling(lookback, min_periods=1).max().fillna(0).astype(bool)
    return (reclaim & recent_sweep).rename("E_prev_day_sweep_reclaim")


def event_range_compression_break(df: pd.DataFrame, lookback: int = 64, q_low: float = 0.2, k_atr: float = 1.4, confirm_bars: int = 4) -> pd.Series:
    trigger_lookback = max(int(confirm_bars), 1)
    rng = df["high"] - df["low"]
    atr = _atr(df, 14)
    low_thr = rng.shift(1).rolling(lookback, min_periods=lookback // 2).quantile(q_low)
    compression_flag = rng <= low_thr
    expansion_flag = rng > (k_atr * atr)
    recent_compression = compression_flag.shift(1).rolling(trigger_lookback, min_periods=1).max().fillna(0).astype(bool)
    return (expansion_flag & recent_compression).rename("E_range_compression_break")


def event_impulse_pullback(df: pd.DataFrame, k_atr: float = 1.2, pullback_min: float = 0.25, pullback_max: float = 0.6, within_bars: int = 6) -> pd.Series:
    trigger_lookback = max(int(within_bars), 1)
    atr = _atr(df, 14)
    body = (df["close"] - df["open"]).abs()
    impulse_flag = body > (k_atr * atr)
    roll_high = df["high"].rolling(20, min_periods=10).max()
    roll_low = df["low"].rolling(20, min_periods=10).min()
    pos = (df["close"] - roll_low) / (roll_high - roll_low).replace(0.0, pd.NA)
    pullback_flag = pos.between(pullback_min, pullback_max)
    recent_impulse = impulse_flag.shift(1).rolling(trigger_lookback, min_periods=1).max().fillna(0).astype(bool)
    return (pullback_flag & recent_impulse).rename("E_impulse_pullback")


def event_liquidity_void_fill_proxy(df: pd.DataFrame, gap_k_atr: float = 1.6, fill_bars: int = 6, ema_span: int = 20) -> pd.Series:
    trigger_lookback = max(int(fill_bars), 1)
    atr = _atr(df, 14)
    rng = df["high"] - df["low"]
    void_flag = rng > (gap_k_atr * atr)
    ema = df["close"].ewm(span=ema_span, adjust=False).mean()
    fill_flag = (df["close"] - ema).abs() <= (0.3 * atr)
    recent_void = void_flag.shift(1).rolling(trigger_lookback, min_periods=1).max().fillna(0).astype(bool)
    return (fill_flag & recent_void).rename("E_liquidity_void_fill_proxy")


def build_event_matrix(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    df = ensure_datetime_index(df)
    cfg = config or {}
    out = pd.DataFrame(index=df.index)
    out["E_prev_day_sweep_reclaim"] = event_prev_day_sweep_reclaim(df, reclaim_bars=int(cfg.get("reclaim_bars", 5)))
    out["E_range_compression_break"] = event_range_compression_break(
        df,
        lookback=int(cfg.get("compression_lookback", 64)),
        q_low=float(cfg.get("compression_q", 0.2)),
        k_atr=float(cfg.get("compression_k_atr", 1.4)),
        confirm_bars=int(cfg.get("confirm_bars", cfg.get("compression_confirm", 4))),
    )
    out["E_impulse_pullback"] = event_impulse_pullback(
        df,
        k_atr=float(cfg.get("impulse_k_atr", 1.2)),
        pullback_min=float(cfg.get("pullback_min", 0.25)),
        pullback_max=float(cfg.get("pullback_max", 0.6)),
        within_bars=int(cfg.get("within_bars", cfg.get("pullback_within", 6))),
    )
    out["E_liquidity_void_fill_proxy"] = event_liquidity_void_fill_proxy(
        df,
        gap_k_atr=float(cfg.get("void_gap_k_atr", 1.6)),
        fill_bars=int(cfg.get("fill_bars", cfg.get("void_fill_bars", 6))),
        ema_span=int(cfg.get("void_ema_span", 20)),
    )
    out["event_mask"] = out.any(axis=1)
    return out
