from __future__ import annotations

from pathlib import Path

import pandas as pd

from edge_discovery.events import build_event_matrix
from edge_discovery.features import build_causal_features
from edge_discovery.labeling import label_range_expansion, label_tp_sl_first
from edge_discovery.time_utils import ensure_datetime_index


def load_ohlc_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [str(c).lower() for c in df.columns]
    df = ensure_datetime_index(df)
    for c in ["open", "high", "low", "close"]:
        if c not in df.columns:
            raise ValueError(f"Missing OHLC column: {c}")
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df.dropna(subset=["open", "high", "low", "close"]).sort_index()


def build_event_dataset(
    ohlc: pd.DataFrame,
    event: str,
    tp_atr: float,
    sl_atr: float,
    horizon: int,
    decision_time: str = "close",
    min_event_coverage: float = 0.02,
    max_event_coverage: float = 0.20,
    event_config: dict | None = None,
    label_mode: str = "tp_sl_first",
    range_k: float = 2.0,
) -> pd.DataFrame:
    ohlc = ensure_datetime_index(ohlc)
    events = build_event_matrix(ohlc, config=event_config)
    features = build_causal_features(ohlc)

    event_cols = [c for c in events.columns if c.startswith("E_")]
    if event == "all":
        selected = event_cols
    else:
        key = f"E_{event}" if not event.startswith("E_") else event
        if key not in event_cols:
            raise ValueError(f"Unknown event '{event}'. Available={event_cols}")
        selected = [key]

    rows = []
    coverage_by_event: dict[str, float] = {}
    for ev_name in selected:
        mask = events[ev_name].astype(bool)
        coverage = float(mask.mean())
        coverage_by_event[ev_name] = coverage
        if coverage < min_event_coverage or coverage > max_event_coverage:
            continue
        if label_mode == "tp_sl_first":
            labels = label_tp_sl_first(
                ohlc,
                mask,
                tp_atr=tp_atr,
                sl_atr=sl_atr,
                horizon=horizon,
                decision_time=decision_time,
            )
        elif label_mode == "range_expansion":
            labels = label_range_expansion(
                ohlc,
                horizon=horizon,
                range_k=range_k,
            )
        else:
            raise ValueError("label_mode must be tp_sl_first|range_expansion")
        ds = pd.concat([features, labels[["label"]]], axis=1).loc[mask].copy()
        ds["event_name"] = ev_name
        ds = ds.dropna(subset=["label"])
        rows.append(ds)

    if not rows:
        coverage_msg = ", ".join(f"{name}={cov:.4%}" for name, cov in coverage_by_event.items())
        raise ValueError(
            "No events passed the coverage gate "
            f"(min={min_event_coverage:.2%}, max={max_event_coverage:.2%}). "
            f"Coverage: {coverage_msg}. "
            "Suggerimento: prova override --reclaim_bars 4 --confirm_bars 4 --within_bars 6 --fill_bars 6"
        )

    out = pd.concat(rows).sort_index()
    out.insert(0, "timestamp", out.index.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"))
    return out


def save_dataset(dataset: pd.DataFrame, out_path: str) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".parquet":
        dataset.to_parquet(out, index=False)
    else:
        dataset.to_csv(out, index=False)
