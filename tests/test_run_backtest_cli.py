import subprocess
import sys
from pathlib import Path

import pytest


def _write_config(path: Path) -> None:
    path.write_text(
        """
universe:
  symbols:
    - EURUSD
  timeframe: M1
bar_contract:
  signal_on: close
  fill_on: open_next
  allow_bar0: false
regime:
  atr_pct_window: 2
  atr_pct_n: 1
strategies:
  enabled:
    - S1_TREND_EMA_ATR_ADX
  params:
    S1_TREND_EMA_ATR_ADX:
      ema_fast: 1
      ema_slow: 2
      atr_period: 1
      adx_period: 1
      k_sl: 1.0
    S2_MR_ZSCORE_EMA_REGIME: {}
    S3_BREAKOUT_ATR_REGIME_EMA200: {}
risk:
  r_base: 1.0
  caps:
    per_strategy: 100.0
    per_symbol: 100.0
    usd_exposure_cap: 1000000.0
  conflict_policy: priority
  priority_order:
    - S1_TREND_EMA_ATR_ADX
  dd_day_limit: 1.0
  dd_week_limit: 1.0
  max_execution_errors: 1
costs:
  spread_baseline_pips:
    EURUSD: 0.0
  slippage:
    slip_base: 0.0
    slip_k: 0.0
    spike_tr_atr_th: 10.0
    spike_mult: 1.0
  scenarios:
    A: 1.0
    B: 1.0
    C: 1.0
validation:
  walk_forward:
    train: 1
    val: 1
    test: 1
  perturb_core_params_pct: 0.0
montecarlo:
  mc1:
    block_min: 1
    block_max: 1
    n_sims: 1
  mc2:
    spread_noise_range: [1.0, 1.0]
    slippage_noise_range: [1.0, 1.0]
    n_sims: 1
outputs:
  runs_dir: ./runs
  write_trades_csv: false
  write_report_json: false
  write_mc_json: false
reproducibility:
  random_seed: 1
""",
        encoding="utf-8",
    )


def _write_csv(path: Path) -> None:
    path.write_text(
        """time,open,high,low,close
2024-01-01T00:00:00,1.0,1.1,0.9,1.0
2024-01-01T00:01:00,1.0,1.1,0.9,1.0
2024-01-01T00:02:00,1.1,1.2,1.0,1.1
2024-01-01T00:03:00,1.2,1.3,1.1,1.2
2024-01-01T00:04:00,1.3,1.4,1.2,1.3
2024-01-01T00:05:00,1.4,1.5,1.3,1.4
""",
        encoding="utf-8",
    )


def test_run_backtest_cli_creates_outputs(tmp_path: Path) -> None:
    pytest.importorskip("pandas")
    config_path = tmp_path / "config.yaml"
    csv_path = tmp_path / "eurusd.csv"
    out_dir = tmp_path / "out"

    _write_config(config_path)
    _write_csv(csv_path)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_backtest.py",
            "--config",
            str(config_path),
            "--eurusd",
            str(csv_path),
            "--out",
            str(out_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert (out_dir / "trades.csv").exists()
    assert (out_dir / "report.json").exists()
