from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Optional

from trading_base.constants import DegradationLevel, Precision

logger = logging.getLogger(__name__)


class DailyLossTracker:
    def __init__(self) -> None:
        self._daily_pnl: Decimal = Decimal("0")

    def record_trade(self, pnl: Decimal) -> None:
        self._daily_pnl = (self._daily_pnl + pnl).quantize(
            Precision.AMOUNT, rounding=ROUND_HALF_EVEN
        )

    def get_daily_pnl(self) -> Decimal:
        return self._daily_pnl

    def is_cap_reached(self, equity: Decimal, daily_loss_cap_pct: Decimal) -> bool:
        from trading_base.risk.sizer import compute_loss_cap
        return self._daily_pnl <= -compute_loss_cap(equity, daily_loss_cap_pct)

    def reset(self) -> None:
        self._daily_pnl = Decimal("0")


class ConsecutiveLossTracker:
    def __init__(self, threshold: int, cooldown_hours: int) -> None:
        self._threshold = threshold
        self._cooldown_hours = cooldown_hours
        self._count: int = 0
        self._last_loss_at: Optional[datetime] = None

    def record_loss(self) -> None:
        self._count += 1
        self._last_loss_at = datetime.now(timezone.utc)
        if self._count >= self._threshold:
            logger.warning(
                "Consecutive loss threshold reached — cooldown active",
                extra={"count": self._count, "expires_at": str(self.cooldown_expires_at())},
            )

    def record_win(self) -> None:
        self._count = 0
        self._last_loss_at = None

    def is_in_cooldown(self) -> bool:
        if self._count < self._threshold:
            return False
        expires = self.cooldown_expires_at()
        if expires is None or datetime.now(timezone.utc) >= expires:
            logger.info("Consecutive loss cooldown elapsed — counter reset")
            self._count = 0
            self._last_loss_at = None
            return False
        return True

    def cooldown_expires_at(self) -> Optional[datetime]:
        if self._last_loss_at is None:
            return None
        return self._last_loss_at + timedelta(hours=self._cooldown_hours)


class EdgeDegradationDetector:
    """Rolling win-rate monitor. Call record_week_end() at close of each trading week."""

    def __init__(
        self,
        rolling_window: int = 10,
        warning_rate: Decimal = Decimal("0.40"),
        reduction_rate: Decimal = Decimal("0.30"),
        suspension_rate: Decimal = Decimal("0.20"),
        reduction_consecutive_weeks: int = 2,
    ) -> None:
        self._window: deque[bool] = deque(maxlen=rolling_window)
        self._rolling_window = rolling_window
        self._warning_rate = warning_rate
        self._reduction_rate = reduction_rate
        self._suspension_rate = suspension_rate
        self._reduction_consecutive_weeks = reduction_consecutive_weeks
        self._consecutive_below_threshold: int = 0
        self._current_level: DegradationLevel = DegradationLevel.NONE

    def record_trade_outcome(self, won: bool) -> None:
        self._window.append(won)
        self._update_level()

    def record_week_end(self) -> None:
        rate = self.get_rolling_win_rate()
        if rate is not None:
            if rate < self._reduction_rate:
                self._consecutive_below_threshold += 1
            else:
                self._consecutive_below_threshold = 0
        self._update_level()

    def get_rolling_win_rate(self) -> Optional[Decimal]:
        if len(self._window) < self._rolling_window:
            return None
        wins = sum(1 for w in self._window if w)
        return Decimal(str(wins / len(self._window))).quantize(
            Precision.RATE, rounding=ROUND_HALF_EVEN
        )

    def current_level(self) -> DegradationLevel:
        return self._current_level

    def check_and_apply(self, risk_pct: Decimal) -> tuple[Decimal, DegradationLevel]:
        """Return adjusted risk_pct and current degradation level."""
        level = self._current_level
        if level == DegradationLevel.SUSPENSION:
            return Decimal("0"), level
        if level == DegradationLevel.REDUCTION:
            return (risk_pct / 2).quantize(Precision.RATE, rounding=ROUND_HALF_EVEN), level
        return risk_pct, level

    def _update_level(self) -> None:
        rate = self.get_rolling_win_rate()
        old = self._current_level

        if rate is None:
            new = DegradationLevel.NONE
        elif rate < self._suspension_rate:
            new = DegradationLevel.SUSPENSION
        elif self._consecutive_below_threshold >= self._reduction_consecutive_weeks:
            new = DegradationLevel.REDUCTION
        elif rate < self._warning_rate:
            new = DegradationLevel.WARNING
        else:
            new = DegradationLevel.NONE

        if new != old:
            log_fn = logger.critical if new in (
                DegradationLevel.REDUCTION, DegradationLevel.SUSPENSION
            ) else logger.warning
            log_fn(
                "Edge degradation level changed",
                extra={"from": old.value, "to": new.value, "win_rate": str(rate)},
            )
            self._current_level = new
