from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from edge_discovery.event_engine_vol import VolEventConfig, compute_volatility_events
from edge_discovery.outcome_metrics import OutcomeConfig, build_event_outcomes, build_unconditional_frame, summarize_outcomes_by_regime
from edge_discovery.regime_classifier import RegimeConfig, classify_vol_regime
from edge_discovery.statistical_tests import StatsConfig, assign_decision_flags, compute_statistical_report


@dataclass(frozen=True)
class VolRegimeResearchConfig:
    event: VolEventConfig = field(default_factory=VolEventConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    outcome: OutcomeConfig = field(default_factory=OutcomeConfig)
    stats: StatsConfig = field(default_factory=StatsConfig)


def run_vol_regime_research(ohlc: pd.DataFrame, cfg: VolRegimeResearchConfig | None = None) -> dict[str, Any]:
    """Run the thesis-driven research workflow (no strategy generation)."""
    config = cfg or VolRegimeResearchConfig()

    events = compute_volatility_events(ohlc, config.event)
    regimes = classify_vol_regime(ohlc, config.regime)

    unconditional = build_unconditional_frame(ohlc, regimes, config.outcome)
    event_outcomes = build_event_outcomes(ohlc, events, regimes, config.outcome)

    outcome_summary = summarize_outcomes_by_regime(event_outcomes, unconditional, config.outcome)
    stats_summary, stability_by_year = compute_statistical_report(
        event_outcomes=event_outcomes,
        unconditional_frame=unconditional,
        horizons=config.outcome.forward_horizons,
        cfg=config.stats,
    )
    stats_with_flags = assign_decision_flags(stats_summary, stability_by_year)

    return {
        "config": {
            "event": asdict(config.event),
            "regime": asdict(config.regime),
            "outcome": asdict(config.outcome),
            "stats": asdict(config.stats),
        },
        "event_flags": events,
        "regime_frame": regimes,
        "event_outcomes": event_outcomes,
        "outcome_summary": outcome_summary,
        "stats_summary": stats_with_flags,
        "stability_per_year": stability_by_year,
    }
