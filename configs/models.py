from __future__ import annotations

from typing import Dict, List, Literal, Tuple

from pydantic import BaseModel, model_validator, validator


ALLOWED_STRATEGIES = {
    "S1_TREND_EMA_ATR_ADX",
    "S2_MR_ZSCORE_EMA_REGIME",
    "S3_BREAKOUT_ATR_REGIME_EMA200",
}


class StrictBaseModel(BaseModel):
    class Config:
        extra = "forbid"
        validate_assignment = True


class Universe(StrictBaseModel):
    symbols: List[str]
    timeframe: str

    @validator("symbols")
    def symbols_non_empty(cls, value: List[str]) -> List[str]:
        if not value:
            raise ValueError("symbols must be a non-empty list")
        return value


class BarContract(StrictBaseModel):
    signal_on: Literal["close"]
    fill_on: Literal["open_next"]
    allow_bar0: bool

    @validator("allow_bar0")
    def allow_bar0_disabled(cls, value: bool) -> bool:
        if value:
            raise ValueError("allow_bar0 must be false")
        return value


class Regime(StrictBaseModel):
    atr_pct_window: int = 960
    atr_pct_n: int = 14
    z_low: float = -0.5
    z_high: float = 0.5
    spike_tr_atr_th: float = 2.5

    @validator("atr_pct_window")
    def atr_pct_window_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("atr_pct_window must be > 0")
        return value

    @validator("atr_pct_n")
    def atr_pct_n_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("atr_pct_n must be > 0")
        return value

    @model_validator(mode="after")
    def zscore_bounds_valid(self) -> "Regime":
        if self.z_low >= self.z_high:
            raise ValueError("z_low must be < z_high")
        return self


class Strategies(StrictBaseModel):
    enabled: List[str]
    params: Dict[str, Dict[str, object]]

    @validator("enabled")
    def enabled_valid(cls, value: List[str]) -> List[str]:
        invalid = [name for name in value if name not in ALLOWED_STRATEGIES]
        if invalid:
            raise ValueError(f"Unknown strategies enabled: {invalid}")
        return value

    @validator("params")
    def params_keys_valid(cls, value: Dict[str, Dict[str, object]]) -> Dict[str, Dict[str, object]]:
        extra = set(value.keys()) - ALLOWED_STRATEGIES
        missing = ALLOWED_STRATEGIES - set(value.keys())
        if extra:
            raise ValueError(f"params contains unsupported strategies: {sorted(extra)}")
        if missing:
            raise ValueError(f"params missing strategies: {sorted(missing)}")
        return value

    @model_validator(mode="after")
    def params_cover_enabled(self) -> "Strategies":
        missing = [name for name in self.enabled if name not in self.params]
        if missing:
            raise ValueError(f"params missing enabled strategies: {missing}")
        return self


class RiskCaps(StrictBaseModel):
    per_strategy: float
    per_symbol: float
    usd_exposure_cap: float


class Risk(StrictBaseModel):
    r_base: float
    caps: RiskCaps
    conflict_policy: Literal["priority", "netting"]
    priority_order: List[str] | None = None
    dd_day_limit: float
    dd_week_limit: float
    max_execution_errors: int
    max_hold_bars: int = 96

    @model_validator(mode="after")
    def priority_requires_order(self) -> "Risk":
        if self.conflict_policy == "priority" and not self.priority_order:
            raise ValueError("priority_order must be provided when conflict_policy is priority")
        if self.conflict_policy == "netting" and self.priority_order:
            raise ValueError("priority_order must be empty when conflict_policy is netting")
        return self


class SlippageModel(StrictBaseModel):
    slip_base: float
    slip_k: float
    spike_tr_atr_th: float
    spike_mult: float


class Costs(StrictBaseModel):
    spread_baseline_pips: Dict[str, float]
    slippage: SlippageModel
    scenarios: Dict[str, float]

    @validator("scenarios")
    def scenarios_have_abc(cls, value: Dict[str, float]) -> Dict[str, float]:
        expected = {"A", "B", "C"}
        missing = expected - set(value.keys())
        extra = set(value.keys()) - expected
        if missing or extra:
            raise ValueError("scenarios must contain only A, B, C")
        return value


class WalkForward(StrictBaseModel):
    train: int | None = None
    val: int | None = None
    test: int | None = None
    train_start: str | None = None
    train_end: str | None = None
    val_start: str | None = None
    val_end: str | None = None
    test_start: str | None = None
    test_end: str | None = None

    @model_validator(mode="after")
    def require_lengths_or_dates(self) -> "WalkForward":
        lengths = [self.train, self.val, self.test]
        date_fields = [
            self.train_start,
            self.train_end,
            self.val_start,
            self.val_end,
            self.test_start,
            self.test_end,
        ]
        if all(value is not None for value in lengths):
            return self
        if all(value is not None for value in date_fields):
            return self
        raise ValueError("walk_forward must include train/val/test lengths or full date splits")


class Validation(StrictBaseModel):
    walk_forward: WalkForward
    perturb_core_params_pct: float


class MonteCarlo1(StrictBaseModel):
    block_min: int
    block_max: int
    n_sims: int

    @model_validator(mode="after")
    def blocks_valid(self) -> "MonteCarlo1":
        if self.block_min > self.block_max:
            raise ValueError("block_min must be <= block_max")
        return self


class MonteCarlo2(StrictBaseModel):
    spread_noise_range: Tuple[float, float]
    slippage_noise_range: Tuple[float, float]
    n_sims: int

    @validator("spread_noise_range", "slippage_noise_range")
    def ranges_valid(cls, value: Tuple[float, float]) -> Tuple[float, float]:
        if len(value) != 2:
            raise ValueError("noise ranges must include two values")
        if value[0] > value[1]:
            raise ValueError("noise range min must be <= max")
        return value


class MonteCarlo(StrictBaseModel):
    mc1: MonteCarlo1
    mc2: MonteCarlo2


class Outputs(StrictBaseModel):
    runs_dir: str
    write_trades_csv: bool
    write_report_json: bool
    write_mc_json: bool
    debug: bool = False


class Reproducibility(StrictBaseModel):
    random_seed: int


class Config(StrictBaseModel):
    universe: Universe
    bar_contract: BarContract
    regime: Regime = Regime()
    strategies: Strategies
    risk: Risk
    costs: Costs
    validation: Validation
    montecarlo: MonteCarlo
    outputs: Outputs
    reproducibility: Reproducibility

    @model_validator(mode="after")
    def costs_cover_symbols(self) -> "Config":
        missing = set(self.universe.symbols) - set(self.costs.spread_baseline_pips.keys())
        if missing:
            raise ValueError(f"spread_baseline_pips missing symbols: {sorted(missing)}")
        return self
