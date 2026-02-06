import pandas as pd


def load_ohlc_csv(path: str) -> pd.DataFrame:
    """
    Load OHLC CSV with datetime index.

    Expected columns:
    time, open, high, low, close, volume (case insensitive)

    Returns:
        DataFrame indexed by UTC datetime.
    """

    df = pd.read_csv(path)

    # normalize column names
    df.columns = [c.lower() for c in df.columns]

    if "time" not in df.columns:
        raise ValueError("CSV must contain 'time' column")

    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time").sort_index()

    required = ["open", "high", "low", "close"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    return df
