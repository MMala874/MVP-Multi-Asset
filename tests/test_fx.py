import pytest

from data.fx import pip_size, to_pips, to_price


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("EURUSD", 0.0001),
        ("GBPUSD", 0.0001),
        ("USDJPY", 0.01),
    ],
)
def test_pip_size(symbol, expected):
    assert pip_size(symbol) == expected


@pytest.mark.parametrize(
    "symbol,price_delta",
    [
        ("EURUSD", 0.0003),
        ("GBPUSD", 0.0007),
        ("USDJPY", 0.02),
    ],
)
def test_to_pips_to_price_roundtrip(symbol, price_delta):
    pips = to_pips(symbol, price_delta)
    assert to_price(symbol, pips) == pytest.approx(price_delta)
