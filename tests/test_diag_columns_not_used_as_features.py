from __future__ import annotations

import pytest

from edge_discovery.modeling import enforce_leakage_firewall


def test_diag_columns_are_blocked_from_feature_set() -> None:
    cols = ["feat_a", "diag_fwd_ret_5", "diag_r_mult_tp1_sl1_H5", "feat_b"]
    with pytest.raises(ValueError, match="diagnostic columns"):
        enforce_leakage_firewall(cols)
