from __future__ import annotations

import argparse

import pandas as pd

from .continuous_builder import build_continuous_contract
from .loader import download_minute
from .normalizer import save_parquet
from .quality import save_quality_report, validate_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Futures minute data pipeline")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD, default: now")
    parser.add_argument("--roll", default="volume", choices=["volume"])
    parser.add_argument("--output", default=None)
    parser.add_argument("--report", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    end = args.end or pd.Timestamp.utcnow().strftime("%Y-%m-%d")

    minute_df = download_minute(symbol=args.symbol, start=args.start, end=end)
    continuous = build_continuous_contract(minute_df, roll_rule=args.roll)
    report = validate_data(continuous)

    output_path = args.output or f"futures_mvp/data/{args.symbol}_continuous_1m.parquet"
    report_path = args.report or f"futures_mvp/data/{args.symbol}_quality_report.json"

    save_parquet(continuous, output_path)
    save_quality_report(report, report_path)

    print(f"Saved continuous data: {output_path}")
    print(f"Saved quality report: {report_path}")
    print(report)


if __name__ == "__main__":
    main()
