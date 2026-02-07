from __future__ import annotations

from pathlib import Path

import pandas as pd

from edge_discovery.event_engine import compute_event_flags
from edge_discovery.feature_engine import compute_features
from edge_discovery.labeler import apply_double_barrier_labels


def build_research_dataset(df: pd.DataFrame, config: dict | None = None, out_dir: str | Path | None = None) -> pd.DataFrame:
    cfg = {
        "k_impulse": 1.5,
        "tp_atr": 1.2,
        "sl_atr": 1.0,
        "horizon": 10,
    }
    if config:
        cfg.update(config)

    events = compute_event_flags(df, k_impulse=float(cfg["k_impulse"]))
    features = compute_features(df, events=events)
    any_event = events.any(axis=1)
    labels = apply_double_barrier_labels(
        df,
        any_event,
        tp_atr=float(cfg["tp_atr"]),
        sl_atr=float(cfg["sl_atr"]),
        horizon=int(cfg["horizon"]),
    )

    ds = pd.concat([events, features, labels], axis=1)
    ds = ds.loc[any_event]
    ds = ds.dropna(subset=["label"])
    ds = ds.dropna(subset=features.columns)
    ds.insert(0, "timestamp", ds.index.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"))

    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        csv_path = out / "research_dataset.csv"
        ds.to_csv(csv_path, index=False)
        try:
            ds.to_parquet(out / "research_dataset.parquet", index=False)
        except Exception:
            pass
        print(f"Saved dataset: {csv_path} rows={len(ds)} cols={len(ds.columns)}")

    return ds


def build_shift_dataset(df: pd.DataFrame, horizons: list[int] | tuple[int, ...] = (5, 10, 20), add_label: bool = True) -> pd.DataFrame:
    del horizons, add_label
    return build_research_dataset(df)
