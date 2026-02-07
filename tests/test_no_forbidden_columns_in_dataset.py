from __future__ import annotations

from pathlib import Path

import pandas as pd

FORBIDDEN_TOKENS = (
    "fwd",
    "mfe",
    "mae",
    "future",
    "next",
    "resolution",
    "outcome",
    "bars_to_resolution",
    "tp_price",
    "sl_price",
)


def test_event_datasets_have_no_forbidden_columns() -> None:
    files = sorted(Path("outputs").glob("ds_*.csv"))
    if not files:
        return

    for f in files:
        df = pd.read_csv(f, nrows=1)
        bad = [c for c in df.columns if any(tok in c.lower() for tok in FORBIDDEN_TOKENS)]
        assert not bad, f"{f} contains forbidden columns: {bad}"
