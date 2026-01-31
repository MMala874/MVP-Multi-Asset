from __future__ import annotations

import copy
from typing import Any, Dict, Union

import pandas as pd

from backtest.orchestrator import BacktestOrchestrator
from configs.loader import load_config
from data.io import load_ohlc_csv


def run_worker_single_scenario(
    config_path: str,
    strategy_id: str,
    param_set: Dict[str, Any],
    df_by_symbol_or_paths: Union[Dict[str, pd.DataFrame], Dict[str, str]],
    scenario: str,
) -> Dict[str, Any]:
    """Worker function: evaluate one parameter set for a single scenario (fast tuning).
    
    Args:
        config_path: Path to YAML config
        strategy_id: Strategy to tune
        param_set: Parameter combination to test
        df_by_symbol_or_paths: Either Dict[symbol -> DataFrame] or Dict[symbol -> CSV path]
        scenario: Scenario to evaluate (A, B, or C)
    
    Returns:
        Dict with params and metrics for the specified scenario only.
        Always includes score_B (using the tuning scenario's profit_factor).
    """
    cfg = load_config(config_path)

    # Support both DataFrames and CSV paths for backward compatibility
    df_by_symbol: Dict[str, pd.DataFrame] = {}
    for symbol, data in df_by_symbol_or_paths.items():
        if data is None:
            continue
        if isinstance(data, pd.DataFrame):
            df_by_symbol[symbol] = data
        else:
            df_by_symbol[symbol] = load_ohlc_csv(data)

    cfg_copy = copy.deepcopy(cfg)
    cfg_copy.strategies.enabled = [strategy_id]
    cfg_copy.strategies.params[strategy_id] = param_set
    cfg_copy.outputs.debug = False  # Silence debug output during tuning

    orchestrator = BacktestOrchestrator()
    trades, report = orchestrator.run(df_by_symbol, cfg_copy, scenarios=[scenario])

    metrics_by_scenario = report.get("metrics", {}).get("by_scenario", {})
    scenario_metrics = metrics_by_scenario.get(scenario, {})

    trades_count = int(scenario_metrics.get("trades", 0))
    expectancy = float(scenario_metrics.get("expectancy", 0.0))
    pf = float(scenario_metrics.get("profit_factor", 0.0))
    max_dd = float(scenario_metrics.get("max_drawdown", 0.0))

    result = {"params": param_set}
    result[f"trades_{scenario}"] = trades_count
    result[f"expectancy_{scenario}"] = expectancy
    result[f"pf_{scenario}"] = pf
    result[f"max_drawdown_{scenario}"] = max_dd

    # Score is based on the tuning scenario's pf
    score = pf
    if trades_count < 300:
        score *= 0.25

    result["score_B"] = score

    return result


def run_worker_full_scenarios(
    config_path: str,
    strategy_id: str,
    param_set: Dict[str, Any],
    df_by_symbol_or_paths: Union[Dict[str, pd.DataFrame], Dict[str, str]],
) -> Dict[str, Any]:
    """Worker function: evaluate one parameter set across all scenarios (full eval for top_k).
    
    Args:
        config_path: Path to YAML config
        strategy_id: Strategy to tune
        param_set: Parameter combination to test
        df_by_symbol_or_paths: Either Dict[symbol -> DataFrame] or Dict[symbol -> CSV path]
    
    Returns:
        Dict with params and metrics for all scenarios, plus score_B.
    """
    cfg = load_config(config_path)

    # Support both DataFrames and CSV paths for backward compatibility
    df_by_symbol: Dict[str, pd.DataFrame] = {}
    for symbol, data in df_by_symbol_or_paths.items():
        if data is None:
            continue
        if isinstance(data, pd.DataFrame):
            df_by_symbol[symbol] = data
        else:
            df_by_symbol[symbol] = load_ohlc_csv(data)

    cfg_copy = copy.deepcopy(cfg)
    cfg_copy.strategies.enabled = [strategy_id]
    cfg_copy.strategies.params[strategy_id] = param_set
    cfg_copy.outputs.debug = False  # Silence debug output during tuning

    orchestrator = BacktestOrchestrator()
    trades, report = orchestrator.run(df_by_symbol, cfg_copy, scenarios=["A", "B", "C"])

    metrics_by_scenario = report.get("metrics", {}).get("by_scenario", {})

    result = {"params": param_set}

    for scen in ["A", "B", "C"]:
        scenario_metrics = metrics_by_scenario.get(scen, {})
        trades_count = int(scenario_metrics.get("trades", 0))
        expectancy = float(scenario_metrics.get("expectancy", 0.0))
        pf = float(scenario_metrics.get("profit_factor", 0.0))
        max_dd = float(scenario_metrics.get("max_drawdown", 0.0))

        result[f"trades_{scen}"] = trades_count
        result[f"expectancy_{scen}"] = expectancy
        result[f"pf_{scen}"] = pf
        result[f"max_drawdown_{scen}"] = max_dd

    # Compute score_B (for consistency with overall scoring)
    trades_b = result.get("trades_B", 0)
    pf_b = result.get("pf_B", 0.0)
    score = pf_b
    if trades_b < 300:
        score *= 0.25

    result["score_B"] = score

    return result


def run_worker(
    config_path: str,
    strategy_id: str,
    param_set: Dict[str, Any],
    df_by_symbol_or_paths: Union[Dict[str, pd.DataFrame], Dict[str, str]],
) -> Dict[str, Any]:
    """Legacy worker function: evaluate one parameter set across all scenarios.
    
    Args:
        config_path: Path to YAML config
        strategy_id: Strategy to tune
        param_set: Parameter combination to test
        df_by_symbol_or_paths: Either Dict[symbol -> DataFrame] or Dict[symbol -> CSV path]
    
    Returns:
        Dict with params and metrics for all scenarios.
    """
    cfg = load_config(config_path)

    # Support both DataFrames and CSV paths for backward compatibility
    df_by_symbol: Dict[str, pd.DataFrame] = {}
    for symbol, data in df_by_symbol_or_paths.items():
        if data is None:
            continue
        if isinstance(data, pd.DataFrame):
            df_by_symbol[symbol] = data
        else:
            df_by_symbol[symbol] = load_ohlc_csv(data)

    cfg_copy = copy.deepcopy(cfg)
    cfg_copy.strategies.enabled = [strategy_id]
    cfg_copy.strategies.params[strategy_id] = param_set
    cfg_copy.outputs.debug = False  # Silence debug output during tuning

    orchestrator = BacktestOrchestrator()
    trades, report = orchestrator.run(df_by_symbol, cfg_copy, scenarios=None)

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
