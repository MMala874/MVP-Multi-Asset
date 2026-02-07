from __future__ import annotations

from edge_discovery.modeling import enforce_leakage_firewall


def test_diag_columns_are_excluded_from_feature_set() -> None:
    cols = ["feat_a", "diag_fwd_ret_5", "diag_r_mult_tp1_sl1_H5", "feat_b"]
    report = enforce_leakage_firewall(cols)
    assert report["allowed"] == ["feat_a", "feat_b"]
    assert sorted(report["diagnostic_excluded"]) == sorted(["diag_fwd_ret_5", "diag_r_mult_tp1_sl1_H5"])
    assert report["blocked"] == []
