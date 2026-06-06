from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType

import pytest

from trading_base.constants import (
    ExitReason, HypotheticalOutcome, OrderState, Regime, RejectionCode, SignalAction,
)
from trading_base.models.order_state import InvalidStateTransitionError, OrderStateMachine
from trading_base.models.rejection import REJECTION_FIELDS, Rejection
from trading_base.models.signal import InvalidSignalError, Signal
from trading_base.models.trade import JOURNAL_FIELDS, Trade


# ── Signal ────────────────────────────────────────────────────────────────────

VALID_PAYLOAD = {
    "symbol": "MES",
    "action": "BUY",
    "strategy": "test-strat",
    "timeframe": "5m",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "signal_price": "4500.00",
    "stop_price": "4490.00",
    "secret": "hunter2",
}


def test_signal_from_webhook_payload():
    sig = Signal.from_webhook_payload(VALID_PAYLOAD, expected_symbol="MES")
    assert sig.symbol == "MES"
    assert sig.action == SignalAction.BUY
    assert isinstance(sig.signal_price, Decimal)
    assert isinstance(sig.stop_price, Decimal)


def test_signal_wrong_symbol_raises():
    with pytest.raises(InvalidSignalError):
        Signal.from_webhook_payload(VALID_PAYLOAD, expected_symbol="QQQ")


def test_signal_validate_hmac():
    sig = Signal.from_webhook_payload(VALID_PAYLOAD, expected_symbol="MES")
    assert sig.validate_hmac("hunter2")
    assert not sig.validate_hmac("wrongsecret")


def test_signal_no_target_price():
    sig = Signal.from_webhook_payload(VALID_PAYLOAD, expected_symbol="MES")
    assert not hasattr(sig, "target_price")


# ── Trade ─────────────────────────────────────────────────────────────────────

def test_trade_journal_fields_count():
    assert len(JOURNAL_FIELDS) == 30


def test_trade_uses_quantity_not_contracts():
    assert "quantity" in JOURNAL_FIELDS
    assert "contracts" not in JOURNAL_FIELDS


def test_trade_market_context_not_spy_position():
    assert "market_context" in JOURNAL_FIELDS
    assert "spy_position" not in JOURNAL_FIELDS


def test_trade_to_csv_row(sample_trade):
    row = sample_trade.to_csv_row()
    assert len(row) == 30


def test_trade_naive_timestamp_raises():
    with pytest.raises(ValueError):
        Trade(
            trade_id="x",
            timestamp_signal=datetime(2026, 1, 1),  # naive — no tzinfo
            timestamp_entry=datetime.now(timezone.utc),
            timestamp_exit=datetime.now(timezone.utc),
            direction=SignalAction.BUY,
            entry_price=Decimal("4500"),
            stop_price=Decimal("4490"),
            target_price=Decimal("4520"),
            stop_distance_points=Decimal("10"),
            target_distance_points=Decimal("20"),
            rr_ratio=Decimal("2"),
            quantity=1,
            support_level=Decimal("4488"),
            resistance_level=Decimal("4522"),
            regime_at_entry=Regime.TRENDING,
            vix_at_entry=Decimal("18"),
            market_context="ABOVE_20MA",
            filters_fired=MappingProxyType({}),
            exit_reason=ExitReason.TAKE_PROFIT,
            exit_price=Decimal("4520"),
            gross_pnl=Decimal("100"),
            commission=Decimal("2"),
            slippage_applied=Decimal("1"),
            net_pnl=Decimal("97"),
            assumption="",
            outcome_note="",
        )


# ── Rejection ─────────────────────────────────────────────────────────────────

def test_rejection_fields_count():
    assert len(REJECTION_FIELDS) == 12


def test_rejection_to_csv_row(sample_rejection):
    row = sample_rejection.to_csv_row()
    assert len(row) == 12


def test_rejection_hypothetical_fields_optional(sample_rejection):
    assert sample_rejection.hypothetical_outcome is None
    assert sample_rejection.hypothetical_pnl is None


# ── OrderStateMachine ─────────────────────────────────────────────────────────

def test_state_machine_starts_idle():
    sm = OrderStateMachine()
    assert sm.state == OrderState.IDLE


def test_state_machine_valid_transitions():
    sm = OrderStateMachine()
    sm.transition(OrderState.ORDER_PENDING)
    assert sm.state == OrderState.ORDER_PENDING
    sm.transition(OrderState.POSITION_OPEN)
    assert sm.state == OrderState.POSITION_OPEN
    sm.transition(OrderState.IDLE)
    assert sm.state == OrderState.IDLE


def test_state_machine_invalid_transition_raises():
    sm = OrderStateMachine()
    with pytest.raises(InvalidStateTransitionError):
        sm.transition(OrderState.POSITION_OPEN)  # IDLE → POSITION_OPEN is illegal


def test_state_machine_reconciling_from_any():
    for initial in (OrderState.IDLE, OrderState.ORDER_PENDING, OrderState.POSITION_OPEN):
        sm = OrderStateMachine()
        if initial != OrderState.IDLE:
            sm.transition(OrderState.ORDER_PENDING)
        if initial == OrderState.POSITION_OPEN:
            sm.transition(OrderState.POSITION_OPEN)
        sm.transition(OrderState.RECONCILING)
        assert sm.state == OrderState.RECONCILING
