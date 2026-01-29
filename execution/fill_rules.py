from __future__ import annotations

import pandas as pd


def get_fill_price(df: pd.DataFrame, idx_t: int, side: str) -> float:
    del side
    idx_next = idx_t + 1
    if idx_next >= len(df):
        raise IndexError("idx_t+1 out of range for fill price")
    return float(df["open"].iat[idx_next])
