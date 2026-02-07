from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """Base strategy contract for the research harness."""

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> pd.Series:
        """Return position intent per bar (-1 short, 0 flat, 1 long)."""

    @abstractmethod
    def risk_model(self, df: pd.DataFrame) -> pd.Series:
        """Return risk scalar per bar (e.g. target contracts or leverage)."""
