from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DDStatus:
    day_dd_breached: bool
    week_dd_breached: bool
    day_drawdown: float
    week_drawdown: float


@dataclass
class DDGuard:
    day_limit: float
    week_limit: float
    day_start_equity: float | None = None
    week_start_equity: float | None = None
    day_anchor: datetime | None = None
    week_anchor: datetime | None = None
    events: list[str] = field(default_factory=list)

    def update(self, equity: float, timestamp: datetime) -> DDStatus:
        self._maybe_reset_day(timestamp, equity)
        self._maybe_reset_week(timestamp, equity)

        day_drawdown = self._calc_drawdown(self.day_start_equity, equity)
        week_drawdown = self._calc_drawdown(self.week_start_equity, equity)

        day_breached = day_drawdown <= -self.day_limit
        week_breached = week_drawdown <= -self.week_limit

        if day_breached:
            self.events.append("day_drawdown_limit_breached")
        if week_breached:
            self.events.append("week_drawdown_limit_breached")

        return DDStatus(
            day_dd_breached=day_breached,
            week_dd_breached=week_breached,
            day_drawdown=day_drawdown,
            week_drawdown=week_drawdown,
        )

    def _maybe_reset_day(self, timestamp: datetime, equity: float) -> None:
        if self.day_anchor is None or timestamp.date() != self.day_anchor.date():
            self.day_anchor = timestamp
            self.day_start_equity = equity
            self.events.append("day_drawdown_anchor_reset")

    def _maybe_reset_week(self, timestamp: datetime, equity: float) -> None:
        if self.week_anchor is None or timestamp.isocalendar().week != self.week_anchor.isocalendar().week:
            self.week_anchor = timestamp
            self.week_start_equity = equity
            self.events.append("week_drawdown_anchor_reset")

    @staticmethod
    def _calc_drawdown(start_equity: float | None, equity: float) -> float:
        if start_equity is None or start_equity == 0:
            return 0.0
        return (equity - start_equity) / start_equity


__all__ = ["DDGuard", "DDStatus"]
