from __future__ import annotations

import numpy as np
import pandas as pd

from edge_discovery.shift_tests import build_base_mask, extract_horizon


def yearly_stability(df: pd.DataFrame, event_col: str, metric_col: str, min_events: int = 30) -> list[dict]:
    horizon = extract_horizon(metric_col)
    rows: list[dict] = []

    for year, part in df.groupby(df.index.year):
        event = part[event_col].astype(int)
        base_mask = build_base_mask(event, horizon)

        ev = part.loc[event == 1, metric_col].dropna().to_numpy(dtype=float)
        base = part.loc[base_mask, metric_col].dropna().to_numpy(dtype=float)

        if ev.size == 0 or base.size == 0:
            delta = np.nan
            sign = 0
        else:
            delta = float(ev.mean() - base.mean())
            sign = int(np.sign(delta))

        rows.append(
            {
                "year": int(year),
                "n_event": int(ev.size),
                "n_base": int(base.size),
                "effect_delta": delta,
                "sign": sign,
                "pass": bool(sign != 0 and ev.size >= min_events),
            }
        )

    return rows
