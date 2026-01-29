from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

import pandas as pd


@dataclass(frozen=True)
class _WalkForwardSpec:
    train: int | None
    val: int | None
    test: int | None
    train_start: str | None
    train_end: str | None
    val_start: str | None
    val_end: str | None
    test_start: str | None
    test_end: str | None


def _extract_walk_forward(config: object) -> _WalkForwardSpec:
    validation = _getattr(config, "validation", config)
    walk_forward = _getattr(validation, "walk_forward", validation)
    return _WalkForwardSpec(
        train=_getattr(walk_forward, "train"),
        val=_getattr(walk_forward, "val"),
        test=_getattr(walk_forward, "test"),
        train_start=_getattr(walk_forward, "train_start"),
        train_end=_getattr(walk_forward, "train_end"),
        val_start=_getattr(walk_forward, "val_start"),
        val_end=_getattr(walk_forward, "val_end"),
        test_start=_getattr(walk_forward, "test_start"),
        test_end=_getattr(walk_forward, "test_end"),
    )


def _getattr(obj: object, name: str, default: object = None) -> object:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _get_index(df_time_index: pd.DataFrame | pd.Series | pd.Index) -> pd.Index:
    if isinstance(df_time_index, pd.Index):
        return df_time_index
    if isinstance(df_time_index, pd.Series):
        return df_time_index.index
    return df_time_index.index


def generate_splits(
    df_time_index: pd.DataFrame | pd.Series | pd.Index,
    config: object,
) -> List[Tuple[Sequence[int], Sequence[int], Sequence[int]]]:
    """Generate walk-forward splits using length or date ranges.

    Returns a list of tuples containing (train_idx, val_idx, test_idx).
    """
    wf = _extract_walk_forward(config)
    index = _get_index(df_time_index)
    if wf.train is not None and wf.val is not None and wf.test is not None:
        return _generate_length_splits(len(index), int(wf.train), int(wf.val), int(wf.test))
    if all(
        value is not None
        for value in (
            wf.train_start,
            wf.train_end,
            wf.val_start,
            wf.val_end,
            wf.test_start,
            wf.test_end,
        )
    ):
        return [
            (
                _date_slice(index, wf.train_start, wf.train_end),
                _date_slice(index, wf.val_start, wf.val_end),
                _date_slice(index, wf.test_start, wf.test_end),
            )
        ]
    raise ValueError("walk_forward must include train/val/test lengths or full date splits")


def _generate_length_splits(
    total_length: int,
    train: int,
    val: int,
    test: int,
) -> List[Tuple[Sequence[int], Sequence[int], Sequence[int]]]:
    splits: List[Tuple[Sequence[int], Sequence[int], Sequence[int]]] = []
    step = test
    window = train + val + test
    start = 0
    while start + window <= total_length:
        train_idx = range(start, start + train)
        val_idx = range(start + train, start + train + val)
        test_idx = range(start + train + val, start + window)
        splits.append((train_idx, val_idx, test_idx))
        start += step
    return splits


def _date_slice(index: pd.Index, start: str, end: str) -> List[int]:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    mask = (index >= start_ts) & (index <= end_ts)
    positions = list(pd.RangeIndex(len(index))[mask])
    return positions


__all__ = ["generate_splits"]
