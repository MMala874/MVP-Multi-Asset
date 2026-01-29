from configs.models import Regime


def test_regime_defaults_atr_pct_n() -> None:
    regime = Regime(atr_pct_window=10)
    assert regime.atr_pct_n == 14
