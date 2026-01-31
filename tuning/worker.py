from __future__ import annotations

import copy
from typing import Any, Dict

import pandas as pd

from backtest.orchestrator import BacktestOrchestrator
from configs.loader import load_config
from data.io import load_ohlc_csv


def run_worker(
    config_path: str,
    strategy_id: str,
    param_set: Dict[str, Any],
    df_paths: Dict[str, str],
) -> Dict[str, Any]:
    """Worker function: evaluate one parameter set across all scenarios.
    
    Args:
        config_path: Path to YAML config
        strategy_id: Strategy to tune
        param_set: Parameter combination to test
        df_paths: Dict mapping symbol -> CSV path
    
    Returns:
        Dict with params and metrics for all scenarios.
    """
    cfg = load_config(config_path)

    df_by_symbol: Dict[str, pd.DataFrame] = {}
    for symbol, path in df_paths.items():
        if path:
            df_by_symbol[symbol] = load_ohlc_csv(path)

    cfg_copy = copy.deepcopy(cfg)
    cfg_copy.strategies.enabled = [strategy_id]
    cfg_copy.strategies.params[strategy_id] = param_set

    orchestrator = BacktestOrchestrator()
    trades, report = orchestrator.run(df_by_symbol, cfg_copy)

    metrics_by_scenario = report.get("metrics", {}).get("by_scenario", {})

    result = {"params": param_set}

    for scenario in ["A", "B", "C"]:
        scenario_metrics = metrics_by_scenario.get(scenario, {})
        trades_count = int(scenario_metrics.get("trades", 0))
        expectancy = float(scenario_metrics.get("expectancy", 0.0))
        pf = float(scenario_metrics.get("profit_factor", 0.0))
        max_dd = float(scenario_metrics.get("max_drawdown", 0.0))

        result[f"trades_{scenario}"] = trades_count
        result[f"expectancy_{scenario}"] = expectancy
        result[f"pf_{scenario}"] = pf
        result[f"max_drawdown_{scenario}"] = max_dd

    trades_b = result.get("trades_B", 0)
    pf_b = result.get("pf_B", 0.0)
    expectancy_b = result.get("expectancy_B", 0.0)
    max_dd_b = result.get("max_drawdown_B", 0.0)

    score = pf_b
    if trades_b < 300:
        score *= 0.25

    result["score_B"] = score
    result["trades_B_raw"] = trades_b

    return result
