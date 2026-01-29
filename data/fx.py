from __future__ import annotations

PIP_SIZES = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
    "USDJPY": 0.01,
}


def pip_size(symbol: str) -> float:
    return PIP_SIZES[symbol]


def to_pips(symbol: str, price_delta: float) -> float:
    return price_delta / pip_size(symbol)


def to_price(symbol: str, pips: float) -> float:
    return pips * pip_size(symbol)
