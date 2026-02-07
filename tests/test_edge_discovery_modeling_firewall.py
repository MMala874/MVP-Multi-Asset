from __future__ import annotations

import pytest

from edge_discovery.modeling import enforce_leakage_firewall


def test_leakage_firewall_allows_slope_features() -> None:
    cols = ["ema50_slope_norm", "reg_slope_20", "volatility_20"]
    report = enforce_leakage_firewall(cols)
    assert report["blocked"] == []
    assert report["allowed"] == cols


@pytest.mark.parametrize(
    "column",
    [
        "tp_price",
        "sl_price",
        "fwd_ret_10",
        "mfe_10_atr",
        "mae_10_atr",
        "bars_to_resolution",
        "outcome_type",
    ],
)
def test_leakage_firewall_blocks_forbidden_tokens(column: str) -> None:
    with pytest.raises(ValueError, match="Leakage firewall triggered"):
        enforce_leakage_firewall(["feature_ok", column])
