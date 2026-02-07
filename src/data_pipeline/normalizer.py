from __future__ import annotations

from pathlib import Path

import pandas as pd


def save_parquet(df: pd.DataFrame, path: str):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output, index=False)
