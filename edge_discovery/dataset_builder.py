from __future__ import annotations

from pathlib import Path

import pandas as pd

from edge_discovery.event_engine import compute_event_flags
from edge_discovery.feature_engine import compute_features
from edge_discovery.conditional_edge import _is_blacklisted_feature
from edge_discovery.labeler import apply_double_barrier_labels


def _attach_prev_day_levels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    day = out.index.normalize()
    day_high = out["high"].resample("1D").max().shift(1)
    day_low = out["low"].resample("1D").min().shift(1)
    out["prev_day_high"] = pd.Series(day_high.reindex(day).to_numpy(), index=out.index)
    out["prev_day_low"] = pd.Series(day_low.reindex(day).to_numpy(), index=out.index)
    return out


def _split_leakage_columns(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    leak_cols = [c for c in dataset.columns if _is_blacklisted_feature(c)]
    diagnostics_cols = ["timestamp", "label", *leak_cols]
    diagnostics = dataset[[c for c in diagnostics_cols if c in dataset.columns]].copy()
    research = dataset.drop(columns=leak_cols, errors="ignore").copy()
    return research, diagnostics


def build_research_dataset(df: pd.DataFrame, config: dict | None = None, out_dir: str | Path | None = None) -> pd.DataFrame:
    cfg = {"tp_atr": 1.2, "sl_atr": 1.0, "horizon": 10}
    if config:
        cfg.update(config)

    base = _attach_prev_day_levels(df)
    events = compute_event_flags(base)
    features = compute_features(base, events=events)

    event_col = "SWEEP_RECLAIM_EXPAND"
    event_mask = events[event_col].eq(1)

    labels = apply_double_barrier_labels(
        base,
        event_mask,
        tp_atr=float(cfg["tp_atr"]),
        sl_atr=float(cfg["sl_atr"]),
        horizon=int(cfg["horizon"]),
    )

    ds = pd.concat([events[[event_col]], features, labels], axis=1)
    ds = ds.loc[event_mask]
    ds = ds.dropna(subset=["label"])
    ds = ds.dropna(subset=features.columns)

    ds.insert(0, "timestamp", ds.index.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"))
    research_ds, diagnostics_ds = _split_leakage_columns(ds)

    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        csv_path = out / "research_dataset_v2.csv"
        parquet_path = out / "research_dataset_v2.parquet"
        diagnostics_path = out / "labels_diagnostics_v2.csv"
        research_ds.to_csv(csv_path, index=False)
        research_ds.to_parquet(parquet_path, index=False)
        diagnostics_ds.to_csv(diagnostics_path, index=False)

        year_counts = research_ds.index.year.value_counts().sort_index().to_dict()
        print(f"rows={len(research_ds)}")
        print(f"label_balance={research_ds['label'].mean():.6f}")
        print(f"year_counts={year_counts}")
        print(f"Saved dataset CSV: {csv_path}")
        print(f"Saved dataset Parquet: {parquet_path}")
        print(f"Saved label diagnostics CSV: {diagnostics_path}")

    return research_ds


def build_shift_dataset(df: pd.DataFrame, horizons: list[int] | tuple[int, ...] = (5, 10, 20), add_label: bool = True) -> pd.DataFrame:
    del horizons, add_label
    return build_research_dataset(df)
