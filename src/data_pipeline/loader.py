from __future__ import annotations

from pathlib import Path

import pandas as pd


DATA_DIR = Path("futures_mvp/data")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = df.rename(
        columns={
            "Datetime": "timestamp",
            "Date": "timestamp",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "Contract": "contract",
            "Symbol": "contract",
        }
    )

    if "timestamp" not in renamed.columns:
        if isinstance(renamed.index, pd.DatetimeIndex):
            renamed = renamed.reset_index(names="timestamp")
        else:
            raise ValueError("No timestamp column found in source data")

    renamed["timestamp"] = pd.to_datetime(renamed["timestamp"], utc=True)
    return renamed.sort_values("timestamp").reset_index(drop=True)


def _load_local(symbol: str, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> pd.DataFrame:
    candidates = [
        DATA_DIR / f"{symbol}_1m.parquet",
        DATA_DIR / f"{symbol}_1m.csv",
        DATA_DIR / f"{symbol}.parquet",
        DATA_DIR / f"{symbol}.csv",
    ]
    for path in candidates:
        if not path.exists():
            continue
        if path.suffix == ".parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path)
        normalized = _normalize_columns(df)
        mask = (normalized["timestamp"] >= start_ts) & (normalized["timestamp"] <= end_ts)
        return normalized.loc[mask].reset_index(drop=True)

    raise FileNotFoundError(
        f"No local minute data found for {symbol} in {DATA_DIR}. Expected one of: "
        f"{', '.join(str(p.name) for p in candidates)}"
    )


def download_minute(symbol: str, start: str, end: str) -> pd.DataFrame:
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")

    if end_ts <= start_ts:
        raise ValueError("'end' must be greater than 'start'")

    try:
        import yfinance as yf  # type: ignore

        ticker = yf.Ticker(f"{symbol}=F")
        remote = ticker.history(start=start_ts.tz_convert(None), end=end_ts.tz_convert(None), interval="1m")
        if not remote.empty:
            return _normalize_columns(remote)
    except Exception:
        pass

    return _load_local(symbol, start_ts, end_ts)
