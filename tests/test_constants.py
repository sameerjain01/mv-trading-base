from __future__ import annotations

from decimal import Decimal

from trading_base.constants import (
    DegradationLevel,
    ExitReason,
    HypotheticalOutcome,
    IBKROrderStatus,
    OrderState,
    OrderTIF,
    Precision,
    ReconciliationState,
    Regime,
    RejectionCode,
    SignalAction,
    TradingMode,
    new_rejection_id,
    new_signal_id,
    new_trade_id,
)


def test_all_enums_importable():
    assert TradingMode.DEV.value == "dev"
    assert TradingMode.PAPER.value == "paper"
    assert TradingMode.LIVE.value == "live"


def test_degradation_level_values():
    assert DegradationLevel.NONE.value == "NONE"
    assert DegradationLevel.WARNING.value == "WARNING"
    assert DegradationLevel.REDUCTION.value == "REDUCTION"
    assert DegradationLevel.SUSPENSION.value == "SUSPENSION"


def test_signal_action_no_flat():
    values = {a.value for a in SignalAction}
    assert "FLAT" not in values
    assert "BUY" in values
    assert "SELL" in values


def test_order_tif_no_ioc():
    values = {t.value for t in OrderTIF}
    assert "IOC" not in values
    assert "DAY" in values
    assert "GTC" in values


def test_precision_amounts_are_decimal():
    assert isinstance(Precision.PRICE, Decimal)
    assert isinstance(Precision.AMOUNT, Decimal)
    assert isinstance(Precision.IBKR_AMOUNT, Decimal)
    assert isinstance(Precision.IBKR_QTY, Decimal)


def test_id_factories_return_strings():
    assert isinstance(new_trade_id(), str)
    assert isinstance(new_rejection_id(), str)
    assert isinstance(new_signal_id(), str)
    assert len(new_trade_id()) == 36  # UUID4 format


def test_rejection_codes_exist():
    required = {
        "SYSTEM_SUSPENDED",
        "SELL_SIGNAL_NO_SHORT_V1",
        "INVALID_SIGNAL_STRUCTURE",
        "OUTSIDE_SESSION_WINDOW",
        "NEWS_BLACKOUT_WINDOW",
        "REGIME_CHOPPY",
        "REGIME_UNKNOWN",
        "DAILY_LOSS_CAP_REACHED",
        "POSITION_EXISTS",
        "CONSECUTIVE_LOSS_COOLDOWN",
        "SPREAD_TOO_WIDE",
        "SIGNAL_PRICE_DEVIATION",
        "MARKET_DATA_UNAVAILABLE",
        "ORDER_IN_FLIGHT",
        "SYSTEM_RECONCILING",
        "CALENDAR_API_UNAVAILABLE",
        "EDGE_DEGRADATION_SUSPENSION",
    }
    names = {r.name for r in RejectionCode}
    for name in required:
        assert name in names, f"RejectionCode.{name} missing"
