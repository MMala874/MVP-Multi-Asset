from pathlib import Path

import pandas as pd

from data.io import load_ohlc_csv


def test_load_ohlc_csv(tmp_path: Path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "time,open,high,low,close,volume\n"
        "2023-01-02 00:00:00,1.2,1.3,1.1,1.25,100\n"
        "2023-01-01 00:00:00,1.0,1.1,0.9,1.05,200\n"
    )

    df = load_ohlc_csv(csv_path)

    assert list(df.columns) == ["time", "open", "high", "low", "close"]
    assert pd.api.types.is_datetime64_any_dtype(df["time"])
    assert df["open"].dtype == float
    assert df["high"].dtype == float
    assert df["low"].dtype == float
    assert df["close"].dtype == float
    assert df["time"].iloc[0] < df["time"].iloc[1]
