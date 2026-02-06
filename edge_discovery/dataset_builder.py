from __future__ import annotations

import pandas as pd

from edge_discovery.event_engine import compute_event_flags
from edge_discovery.feature_engine import compute_features
from edge_discovery.forward_metrics import compute_forward_metrics


def build_shift_dataset(df: pd.DataFrame, horizons: list[int] | tuple[int, ...] = (5, 10, 20)) -> pd.DataFrame:
    events = compute_event_flags(df)
    feats = compute_features(df)
    fwd = compute_forward_metrics(df, horizons=horizons)

    dataset = pd.concat([events, feats, fwd], axis=1)
    dataset = dataset.loc[events.any(axis=1)]
    dataset = dataset.dropna()
    return dataset


# backward compatibility alias
build_research_dataset = build_shift_dataset
