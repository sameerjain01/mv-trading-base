from __future__ import annotations

from decimal import Decimal

import pytest

from trading_base.constants import DegradationLevel
from trading_base.risk.sizer import (
    compute_gross_pnl,
    compute_loss_cap,
    compute_position_size,
    compute_target_price,
)
from trading_base.risk.trackers import (
    ConsecutiveLossTracker,
    DailyLossTracker,
    EdgeDegradationDetector,
)


# ── DailyLossTracker ──────────────────────────────────────────────────────────

def test_daily_loss_tracker_accumulates():
    t = DailyLossTracker()
    t.record_trade(Decimal("-100"))
    t.record_trade(Decimal("-50"))
    assert t.get_daily_pnl() == Decimal("-150")


def test_daily_loss_tracker_breach():
    t = DailyLossTracker()
    t.record_trade(Decimal("-201"))
    # 2% of 10000 = 200
    assert t.is_cap_reached(Decimal("10000"), Decimal("0.02"))


def test_daily_loss_tracker_not_breached():
    t = DailyLossTracker()
    t.record_trade(Decimal("-100"))
    assert not t.is_cap_reached(Decimal("10000"), Decimal("0.02"))


def test_daily_loss_tracker_reset():
    t = DailyLossTracker()
    t.record_trade(Decimal("-500"))
    t.reset()
    assert t.get_daily_pnl() == Decimal("0")


# ── ConsecutiveLossTracker ────────────────────────────────────────────────────

def test_consecutive_loss_tracker_not_in_cooldown_initially():
    t = ConsecutiveLossTracker(threshold=3, cooldown_hours=4)
    assert not t.is_in_cooldown()


def test_consecutive_loss_tracker_triggers_at_threshold():
    t = ConsecutiveLossTracker(threshold=3, cooldown_hours=4)
    t.record_loss()
    t.record_loss()
    assert not t.is_in_cooldown()
    t.record_loss()
    assert t.is_in_cooldown()


def test_consecutive_loss_tracker_reset_on_win():
    t = ConsecutiveLossTracker(threshold=3, cooldown_hours=4)
    t.record_loss()
    t.record_loss()
    t.record_win()
    assert not t.is_in_cooldown()


def test_consecutive_loss_tracker_expires(monkeypatch):
    import trading_base.risk.trackers as mod
    from datetime import datetime, timedelta, timezone
    # Set last_loss_at to 5 hours ago (cooldown is 4h)
    t = ConsecutiveLossTracker(threshold=1, cooldown_hours=4)
    t.record_loss()
    past = datetime.now(timezone.utc) - timedelta(hours=5)
    t._last_loss_at = past
    assert not t.is_in_cooldown()


# ── EdgeDegradationDetector ───────────────────────────────────────────────────

def test_degradation_none_initially():
    d = EdgeDegradationDetector(rolling_window=5)
    assert d.current_level() == DegradationLevel.NONE


def test_degradation_none_insufficient_data():
    d = EdgeDegradationDetector(rolling_window=5)
    d.record_trade_outcome(True)
    d.record_trade_outcome(False)
    assert d.current_level() == DegradationLevel.NONE  # only 2/5 data points


def test_degradation_escalates_to_warning():
    d = EdgeDegradationDetector(
        rolling_window=5,
        warning_rate=Decimal("0.50"),
        reduction_rate=Decimal("0.30"),
        suspension_rate=Decimal("0.15"),
    )
    for _ in range(3):
        d.record_trade_outcome(False)
    for _ in range(2):
        d.record_trade_outcome(True)
    # 40% win rate — below warning threshold
    assert d.current_level() in (DegradationLevel.WARNING, DegradationLevel.NONE)


def test_degradation_suspension():
    d = EdgeDegradationDetector(
        rolling_window=5,
        warning_rate=Decimal("0.50"),
        reduction_rate=Decimal("0.30"),
        suspension_rate=Decimal("0.15"),
    )
    for _ in range(5):
        d.record_trade_outcome(False)
    assert d.current_level() == DegradationLevel.SUSPENSION


def test_check_and_apply_suspension_returns_zero():
    d = EdgeDegradationDetector(rolling_window=5, suspension_rate=Decimal("0.99"))
    for _ in range(5):
        d.record_trade_outcome(False)
    adjusted, level = d.check_and_apply(Decimal("0.01"))
    assert adjusted == Decimal("0")
    assert level == DegradationLevel.SUSPENSION


# ── Sizer ─────────────────────────────────────────────────────────────────────

def test_compute_position_size_basic():
    qty = compute_position_size(
        equity=Decimal("10000"),
        risk_pct=Decimal("0.01"),
        stop_distance=Decimal("10"),
        point_value=Decimal("5"),
    )
    # risk = 100, cost_per_unit = 50, result = 2
    assert qty == 2
    assert isinstance(qty, int)


def test_compute_position_size_zero_when_too_small():
    qty = compute_position_size(
        equity=Decimal("500"),
        risk_pct=Decimal("0.01"),
        stop_distance=Decimal("10"),
        point_value=Decimal("5"),
    )
    assert qty == 0


def test_compute_position_size_zero_distance():
    assert compute_position_size(Decimal("10000"), Decimal("0.01"), Decimal("0"), Decimal("5")) == 0


def test_compute_loss_cap_type():
    cap = compute_loss_cap(Decimal("10000"), Decimal("0.02"))
    assert isinstance(cap, Decimal)
    assert cap == Decimal("200.00")


def test_compute_gross_pnl_type():
    pnl = compute_gross_pnl(
        entry_price=Decimal("4500"),
        exit_price=Decimal("4520"),
        quantity=1,
        point_value=Decimal("5"),
    )
    assert isinstance(pnl, Decimal)
    assert pnl == Decimal("100.0000")


def test_compute_target_price():
    target = compute_target_price(
        entry_price=Decimal("4500"),
        stop_price=Decimal("4490"),
        rr_ratio=Decimal("2"),
    )
    # target = 4500 + (4500 - 4490) * 2 = 4500 + 20 = 4520
    assert target == Decimal("4520.0000")
    assert isinstance(target, Decimal)
