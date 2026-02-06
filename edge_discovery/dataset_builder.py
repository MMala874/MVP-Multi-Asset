from __future__ import annotations

import pandas as pd

from edge_discovery.event_engine import compute_event_flags
from edge_discovery.feature_engine import compute_normalized_features
from edge_discovery.labeler import label_event_bars


def build_research_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Build a research-ready event-gated dataset with labels.

    Pipeline:
    1) Event computation
    2) Feature computation
    3) Event-gated row filtering
    4) Double-barrier labeling
    5) NaN cleanup for labels and features
    """
    events = compute_event_flags(df)
    features = compute_normalized_features(df)

    any_event = events.any(axis=1)
    labels = label_event_bars(df=df, event_mask=any_event)

    dataset = pd.concat([events, features, labels], axis=1)
    dataset = dataset.loc[any_event]
    dataset = dataset.dropna(subset=["label"])

    feature_columns = list(features.columns)
    dataset = dataset.dropna(subset=feature_columns)

    dataset = dataset.copy()
    dataset["timestamp"] = dataset.index
    return dataset
