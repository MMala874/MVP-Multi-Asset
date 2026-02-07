from __future__ import annotations

import numpy as np
import pandas as pd

from edge_discovery.event_dataset import build_event_dataset
from edge_discovery.labeling import label_directional_expansion


def _mini_ohlc(n: int = 40) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    close = 100 + np.linspace(0.0, 1.0, n)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) + 0.5
    low = np.minimum(open_, close) - 0.5
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


def test_directional_label_uses_only_forward_window() -> None:
    horizon = 5
    event_i = 10

    df = _mini_ohlc()
    mask = pd.Series(False, index=df.index)
    mask.iloc[event_i] = True

    base = label_directional_expansion(df, mask, horizon=horizon, dir_k=1.0)

    modified_future = df.copy()
    modified_future.iloc[event_i + horizon + 3 :, modified_future.columns.get_loc("high")] += 100.0
    modified_future.iloc[event_i + horizon + 3 :, modified_future.columns.get_loc("low")] -= 100.0
    after_window = label_directional_expansion(modified_future, mask, horizon=horizon, dir_k=1.0)

    assert base.loc[df.index[event_i], "label"] == after_window.loc[df.index[event_i], "label"]

    modified_inside = df.copy()
    modified_inside.iloc[event_i + 2, modified_inside.columns.get_loc("high")] += 8.0
    inside_window = label_directional_expansion(modified_inside, mask, horizon=horizon, dir_k=1.0)

    assert base.loc[df.index[event_i], "label"] != inside_window.loc[df.index[event_i], "label"]


def test_directional_dataset_has_no_prohibited_columns() -> None:
    df = _mini_ohlc(n=300)
    ds = build_event_dataset(
        df,
        event="vol_compress_expand",
        tp_atr=1.5,
        sl_atr=1.0,
        horizon=10,
        min_event_coverage=0.0,
        max_event_coverage=1.0,
        label_mode="directional_expansion",
        dir_k=1.0,
        event_config={"compress_window": 20, "compress_q": 0.4},
    )

    forbidden = {"diag_up_move", "diag_down_move", "diag_thr", "entry_price", "tp_price", "sl_price"}
    assert forbidden.isdisjoint(set(ds.columns))
