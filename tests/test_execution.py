import pandas as pd

from configs.models import Costs, SlippageModel
from execution.cost_model import CostModel
from execution.fill_rules import get_fill_price


class DummyConfig:
    def __init__(self) -> None:
        self.costs = Costs(
            spread_baseline_pips={"EURUSD": 1.0},
            slippage=SlippageModel(
                slip_base=0.1,
                slip_k=0.5,
                spike_tr_atr_th=1.5,
                spike_mult=2.0,
            ),
            scenarios={"A": 1.0, "B": 1.0, "C": 1.0},
        )


def test_fill_open_next():
    df = pd.DataFrame({"open": [1.1, 1.2, 1.3]})
    assert get_fill_price(df, idx_t=0, side="buy") == 1.2


def test_costs_symmetric_entry_exit():
    df = pd.DataFrame(
        {
            "high": [1.1, 1.2, 1.3],
            "low": [1.0, 1.1, 1.2],
            "close": [1.05, 1.15, 1.25],
        }
    )
    atr_series = pd.Series([1.0, 2.0, 2.0])
    model = CostModel(DummyConfig())
    entry_cost, exit_cost = model.trade_cost_pips(
        symbol="EURUSD",
        idx_t=1,
        scenario="A",
        df=df,
        atr_series=atr_series,
    )
    assert entry_cost == exit_cost


def test_no_leakage_atr_usage():
    df = pd.DataFrame(
        {
            "high": [10.0, 11.0, 12.0, 13.0],
            "low": [9.0, 10.0, 11.0, 12.0],
            "close": [9.5, 10.5, 11.5, 12.5],
        }
    )
    df_modified = df.copy()
    df_modified.loc[2, "high"] = 20.0
    df_modified.loc[2, "low"] = 8.0

    atr_series = pd.Series([1.0, 2.0, 5.0, 6.0])

    model = CostModel(DummyConfig())
    slippage = model.slippage_pips(
        df_modified,
        idx_t=1,
        symbol="EURUSD",
        atr_series=atr_series,
        scenario="A",
    )

    tr_next = max(
        20.0 - 8.0,
        abs(20.0 - 10.5),
        abs(8.0 - 10.5),
    )
    expected = 0.1 + 0.5 * (tr_next / atr_series.iat[1])
    assert slippage == expected
