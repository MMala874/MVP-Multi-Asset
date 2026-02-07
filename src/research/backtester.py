from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .strategy_template import Strategy


@dataclass(frozen=True)
class BacktestConfig:
    commission_per_contract: float = 0.0
    slippage_base: float = 0.0
    slippage_vol_coeff: float = 0.0
    initial_capital: float = 100_000.0


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity_curve: pd.Series
    metrics: dict[str, Any]


class Backtester:
    def __init__(self, config: BacktestConfig) -> None:
        self.config = config

    def run(self, df: pd.DataFrame, strategy: Strategy) -> BacktestResult:
        data = df.copy()
        for col in ("close", "atr"):
            if col not in data:
                raise ValueError(f"Missing required column: {col}")

        signal = strategy.generate_signal(data).astype(float).reindex(data.index).fillna(0.0).clip(-1, 1)
        risk = strategy.risk_model(data).astype(float).reindex(data.index).fillna(0.0)
        position = signal * risk

        ret = data["close"].pct_change().fillna(0.0)
        gross_pnl = position.shift(1).fillna(0.0) * ret

        turnover = position.diff().abs().fillna(position.abs())
        commission = turnover * float(self.config.commission_per_contract)
        slippage = turnover * (float(self.config.slippage_base) + float(self.config.slippage_vol_coeff) * data["atr"].fillna(0.0))

        net_pnl = gross_pnl - commission - slippage
        equity_curve = (1.0 + net_pnl).cumprod() * float(self.config.initial_capital)

        trades = self._build_trade_log(data, position, commission, slippage, net_pnl)
        metrics = self._compute_metrics(net_pnl, equity_curve)
        return BacktestResult(trades=trades, equity_curve=equity_curve, metrics=metrics)

    def export(self, result: BacktestResult, output_dir: str | Path) -> None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        result.trades.to_csv(out / "trades.csv", index=False)
        with (out / "metrics.json").open("w", encoding="utf-8") as f:
            json.dump(result.metrics, f, indent=2)
        result.equity_curve.rename("equity").to_csv(out / "equity_curve.csv", header=True)

    @staticmethod
    def _build_trade_log(
        df: pd.DataFrame,
        position: pd.Series,
        commission: pd.Series,
        slippage: pd.Series,
        net_pnl: pd.Series,
    ) -> pd.DataFrame:
        change = position.diff().fillna(position)
        rows: list[dict[str, Any]] = []
        for i, delta in enumerate(change):
            if np.isclose(delta, 0.0):
                continue
            rows.append(
                {
                    "timestamp": df.index[i],
                    "price": float(df["close"].iloc[i]),
                    "delta_contracts": float(delta),
                    "position_after": float(position.iloc[i]),
                    "commission": float(commission.iloc[i]),
                    "slippage": float(slippage.iloc[i]),
                    "bar_net_pnl": float(net_pnl.iloc[i]),
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _compute_metrics(net_pnl: pd.Series, equity_curve: pd.Series) -> dict[str, Any]:
        total_return = float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1.0) if len(equity_curve) > 1 else 0.0
        vol = float(net_pnl.std(ddof=0))
        sharpe = float((net_pnl.mean() / vol) * np.sqrt(252)) if vol > 0 else 0.0
        running_peak = equity_curve.cummax()
        drawdown = (equity_curve / running_peak - 1.0).min()
        return {
            "total_return": total_return,
            "sharpe": sharpe,
            "max_drawdown": float(drawdown),
            "n_bars": int(len(net_pnl)),
            "n_trades": int((net_pnl != 0).sum()),
        }
