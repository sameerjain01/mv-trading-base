from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from trading_base.constants import OrderState, Regime, RejectionCode, SignalAction, TradingMode
from trading_base.gates.framework import GateResult
from trading_base.gates.gates import (
    gate_news_blackout,
    gate_portfolio_state,
    gate_position_state_lock,
    gate_price_deviation,
    gate_regime,
    gate_sequence_risk,
    gate_signal_direction,
    gate_spread,
    gate_suspended,
)
from trading_base.risk.trackers import ConsecutiveLossTracker


# ── GateResult ────────────────────────────────────────────────────────────────

def test_gate_result_ok():
    r = GateResult.ok()
    assert r.passed
    assert r.rejection_code is None


def test_gate_result_fail():
    r = GateResult.fail(RejectionCode.REGIME_CHOPPY, "choppy")
    assert not r.passed
    assert r.rejection_code == RejectionCode.REGIME_CHOPPY
    assert r.reason == "choppy"


# ── gate_suspended ────────────────────────────────────────────────────────────

def test_gate_suspended_no_file():
    assert gate_suspended(None).passed
    assert gate_suspended(Path("nonexistent/SUSPENDED")).passed


def test_gate_suspended_file_exists(tmp_path):
    f = tmp_path / "SUSPENDED"
    f.write_text("manual halt")
    r = gate_suspended(f)
    assert not r.passed
    assert r.rejection_code == RejectionCode.SYSTEM_SUSPENDED
    assert "manual halt" in r.reason


# ── gate_signal_direction ─────────────────────────────────────────────────────

class _FakeSignal:
    def __init__(self, action):
        self.action = action
        self.symbol = "MES"
        self.signal_price = Decimal("4500")
        self.stop_price = Decimal("4490")
        from datetime import datetime, timezone
        self.timestamp_signal = datetime.now(timezone.utc)


def test_gate_signal_direction_buy_allowed():
    sig = _FakeSignal(SignalAction.BUY)
    assert gate_signal_direction(sig).passed


def test_gate_signal_direction_sell_blocked_by_default():
    sig = _FakeSignal(SignalAction.SELL)
    r = gate_signal_direction(sig)
    assert not r.passed
    assert r.rejection_code == RejectionCode.SELL_SIGNAL_NO_SHORT_V1


def test_gate_signal_direction_sell_allowed_when_configured():
    sig = _FakeSignal(SignalAction.SELL)
    assert gate_signal_direction(sig, allowed_directions=[SignalAction.BUY, SignalAction.SELL]).passed


# ── gate_regime ───────────────────────────────────────────────────────────────

def test_gate_regime_trending_passes():
    assert gate_regime(Regime.TRENDING).passed


def test_gate_regime_neutral_passes():
    assert gate_regime(Regime.NEUTRAL).passed


def test_gate_regime_choppy_fails():
    r = gate_regime(Regime.CHOPPY)
    assert not r.passed
    assert r.rejection_code == RejectionCode.REGIME_CHOPPY


def test_gate_regime_unknown_fails():
    r = gate_regime(Regime.UNKNOWN)
    assert not r.passed
    assert r.rejection_code == RejectionCode.REGIME_UNKNOWN


def test_gate_regime_custom_acceptable():
    assert gate_regime(Regime.CHOPPY, acceptable_regimes=[Regime.CHOPPY]).passed


# ── gate_portfolio_state ──────────────────────────────────────────────────────

def test_gate_portfolio_state_passes():
    r = gate_portfolio_state(
        daily_loss=Decimal("-50"),
        order_state=OrderState.IDLE,
        equity=Decimal("10000"),
        daily_loss_cap_pct=Decimal("0.02"),
    )
    assert r.passed


def test_gate_portfolio_state_daily_loss_cap():
    r = gate_portfolio_state(
        daily_loss=Decimal("-201"),
        order_state=OrderState.IDLE,
        equity=Decimal("10000"),
        daily_loss_cap_pct=Decimal("0.02"),
    )
    assert not r.passed
    assert r.rejection_code == RejectionCode.DAILY_LOSS_CAP_REACHED


def test_gate_portfolio_state_position_exists():
    r = gate_portfolio_state(
        daily_loss=Decimal("0"),
        order_state=OrderState.POSITION_OPEN,
        equity=Decimal("10000"),
        daily_loss_cap_pct=Decimal("0.02"),
    )
    assert not r.passed
    assert r.rejection_code == RejectionCode.POSITION_EXISTS


# ── gate_position_state_lock ──────────────────────────────────────────────────

def test_gate_position_state_lock_idle_passes():
    assert gate_position_state_lock(OrderState.IDLE).passed


def test_gate_position_state_lock_order_pending_fails():
    r = gate_position_state_lock(OrderState.ORDER_PENDING)
    assert not r.passed
    assert r.rejection_code == RejectionCode.ORDER_IN_FLIGHT


def test_gate_position_state_lock_reconciling_fails():
    r = gate_position_state_lock(OrderState.RECONCILING)
    assert not r.passed
    assert r.rejection_code == RejectionCode.SYSTEM_RECONCILING


# ── gate_sequence_risk ────────────────────────────────────────────────────────

def test_gate_sequence_risk_passes_initially():
    tracker = ConsecutiveLossTracker(threshold=3, cooldown_hours=4)
    assert gate_sequence_risk(tracker).passed


def test_gate_sequence_risk_fails_in_cooldown():
    tracker = ConsecutiveLossTracker(threshold=1, cooldown_hours=4)
    tracker.record_loss()
    r = gate_sequence_risk(tracker)
    assert not r.passed
    assert r.rejection_code == RejectionCode.CONSECUTIVE_LOSS_COOLDOWN


# ── gate_spread ───────────────────────────────────────────────────────────────

def test_gate_spread_dev_mode_always_passes():
    r = gate_spread(None, None, Decimal("0.25"), 4, TradingMode.DEV)
    assert r.passed


def test_gate_spread_passes_within_limit():
    r = gate_spread(Decimal("4499.75"), Decimal("4500.00"), Decimal("0.25"), 4, TradingMode.PAPER)
    assert r.passed


def test_gate_spread_fails_when_too_wide():
    r = gate_spread(Decimal("4498.00"), Decimal("4500.00"), Decimal("0.25"), 4, TradingMode.PAPER)
    assert not r.passed
    assert r.rejection_code == RejectionCode.SPREAD_TOO_WIDE


def test_gate_spread_unavailable_data():
    r = gate_spread(None, None, Decimal("0.25"), 4, TradingMode.PAPER)
    assert not r.passed
    assert r.rejection_code == RejectionCode.MARKET_DATA_UNAVAILABLE


# ── gate_price_deviation ──────────────────────────────────────────────────────

def test_gate_price_deviation_dev_mode_passes():
    r = gate_price_deviation(Decimal("9999"), None, None, Decimal("0.25"), 8, TradingMode.DEV)
    assert r.passed


def test_gate_price_deviation_passes_within_limit():
    r = gate_price_deviation(
        Decimal("4500.00"), Decimal("4499.50"), Decimal("4500.50"),
        Decimal("0.25"), 8, TradingMode.PAPER,
    )
    assert r.passed


def test_gate_price_deviation_fails_when_stale():
    r = gate_price_deviation(
        Decimal("4510.00"), Decimal("4499.50"), Decimal("4500.50"),
        Decimal("0.25"), 8, TradingMode.PAPER,
    )
    assert not r.passed
    assert r.rejection_code == RejectionCode.SIGNAL_PRICE_DEVIATION


# ── gate_news_blackout ────────────────────────────────────────────────────────

def test_gate_news_blackout_no_events_passes():
    r = gate_news_blackout(datetime.now(timezone.utc), [], 30)
    assert r.passed


def test_gate_news_blackout_unavailable_fails():
    r = gate_news_blackout(datetime.now(timezone.utc), None, 30)
    assert not r.passed
    assert r.rejection_code == RejectionCode.CALENDAR_API_UNAVAILABLE


def test_gate_news_blackout_event_within_window_fails():
    from dataclasses import dataclass

    @dataclass
    class _Evt:
        name: str
        event_time: datetime

    now = datetime.now(timezone.utc)
    evt = _Evt(name="FOMC", event_time=now)
    r = gate_news_blackout(now, [evt], 30)
    assert not r.passed
    assert r.rejection_code == RejectionCode.NEWS_BLACKOUT_WINDOW
