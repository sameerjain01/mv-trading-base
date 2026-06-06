from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from trading_base.constants import (
    OrderState,
    Regime,
    RejectionCode,
    SignalAction,
    TradingMode,
)
from trading_base.gates.framework import GateResult
from trading_base.risk.sizer import compute_loss_cap
from trading_base.timezone import MarketTime

if TYPE_CHECKING:
    from trading_base.models.signal import Signal
    from trading_base.risk.trackers import ConsecutiveLossTracker


# ── Gate 0 — System suspended ─────────────────────────────────────────────────

def gate_suspended(suspended_file: Optional[Path]) -> GateResult:
    if suspended_file is None or not suspended_file.exists():
        return GateResult.ok()
    try:
        reason = suspended_file.read_text(encoding="utf-8").strip()
    except OSError:
        reason = ""
    return GateResult.fail(
        RejectionCode.SYSTEM_SUSPENDED,
        reason or "system suspended — delete state/SUSPENDED to resume",
    )


# ── Gate 1 — Signal direction ─────────────────────────────────────────────────

def gate_signal_direction(
    signal: "Signal",
    allowed_directions: Optional[list[SignalAction]] = None,
) -> GateResult:
    """Reject signals whose action is not in allowed_directions.

    Default allowed_directions is [BUY] (long-only v1 policy).
    Pass [BUY, SELL] for strategies that support both sides.
    """
    if allowed_directions is None:
        allowed_directions = [SignalAction.BUY]
    if signal.action not in allowed_directions:
        return GateResult.fail(
            RejectionCode.SELL_SIGNAL_NO_SHORT_V1,
            f"signal action {signal.action.value} not in allowed directions",
        )
    return GateResult.ok()


# ── Gate 2 — Signal structural validity ───────────────────────────────────────

def gate_signal_validity(
    signal: "Signal",
    expected_symbol: str,
    staleness_seconds: int,
) -> GateResult:
    if signal.symbol != expected_symbol:
        return GateResult.fail(
            RejectionCode.INVALID_SIGNAL_STRUCTURE,
            f"symbol {signal.symbol!r} is not {expected_symbol!r}",
        )
    now = datetime.now(signal.timestamp_signal.tzinfo or __import__("datetime").timezone.utc)
    from datetime import timezone
    now = datetime.now(timezone.utc)
    ts = signal.timestamp_signal.astimezone(timezone.utc)
    age = (now - ts).total_seconds()
    if not (0 <= age <= staleness_seconds):
        return GateResult.fail(
            RejectionCode.INVALID_SIGNAL_STRUCTURE,
            f"signal timestamp is {age:.0f}s old (limit {staleness_seconds}s)",
        )
    if signal.signal_price <= 0:
        return GateResult.fail(
            RejectionCode.INVALID_SIGNAL_STRUCTURE,
            "signal_price must be positive",
        )
    if signal.action == SignalAction.BUY and signal.stop_price >= signal.signal_price:
        return GateResult.fail(
            RejectionCode.INVALID_SIGNAL_STRUCTURE,
            f"stop_price {signal.stop_price} must be below signal_price {signal.signal_price} for BUY",
        )
    return GateResult.ok()


# ── Gate 3 — Session window ───────────────────────────────────────────────────

def gate_session_window(
    current_time: datetime,
    timezone_name: str,
    open_hour: int,
    open_minute: int,
    close_hour: int,
    close_minute: int,
    blackout_open_minutes: int,
    blackout_close_minutes: int,
) -> GateResult:
    local = MarketTime(market_tz=timezone_name).to_et(current_time)

    session_open = local.replace(hour=open_hour, minute=open_minute, second=0, microsecond=0)
    session_close = local.replace(hour=close_hour, minute=close_minute, second=0, microsecond=0)
    entry_start = session_open + timedelta(minutes=blackout_open_minutes)
    entry_end = session_close - timedelta(minutes=blackout_close_minutes)

    cross_midnight = (open_hour * 60 + open_minute) >= (close_hour * 60 + close_minute)

    if cross_midnight:
        weekday = local.weekday()
        if weekday == 5:
            return GateResult.fail(RejectionCode.OUTSIDE_SESSION_WINDOW, "exchange closed: Saturday")
        if weekday == 6 and local < session_open:
            return GateResult.fail(
                RejectionCode.OUTSIDE_SESSION_WINDOW,
                f"exchange not yet open: {local.strftime('%H:%M')} ET",
            )
        if weekday == 4 and local >= session_close:
            return GateResult.fail(
                RejectionCode.OUTSIDE_SESSION_WINDOW,
                f"exchange closed for weekend: {local.strftime('%H:%M')} ET",
            )
        if weekday < 4 and not (local >= session_open or local < session_close):
            return GateResult.fail(
                RejectionCode.OUTSIDE_SESSION_WINDOW,
                f"maintenance break: {local.strftime('%H:%M')} ET",
            )
        if local >= session_open and local < entry_start:
            return GateResult.fail(
                RejectionCode.OUTSIDE_SESSION_WINDOW,
                f"within open blackout ({blackout_open_minutes}min after open)",
            )
        if local >= entry_end and local < session_close:
            return GateResult.fail(
                RejectionCode.OUTSIDE_SESSION_WINDOW,
                f"within close blackout ({blackout_close_minutes}min before close)",
            )
    else:
        if local < session_open or local >= session_close:
            return GateResult.fail(
                RejectionCode.OUTSIDE_SESSION_WINDOW,
                f"outside session: {local.strftime('%H:%M')} ET",
            )
        if local < entry_start:
            return GateResult.fail(
                RejectionCode.OUTSIDE_SESSION_WINDOW,
                f"within open blackout ({blackout_open_minutes}min after open)",
            )
        if local >= entry_end:
            return GateResult.fail(
                RejectionCode.OUTSIDE_SESSION_WINDOW,
                f"within close blackout ({blackout_close_minutes}min before close)",
            )

    return GateResult.ok()


# ── Gate 4 — News blackout ────────────────────────────────────────────────────

def gate_news_blackout(
    current_time: datetime,
    events,                          # list[EconomicEvent] | None
    blackout_minutes: int,
) -> GateResult:
    if events is None:
        return GateResult.fail(
            RejectionCode.CALENDAR_API_UNAVAILABLE,
            "economic calendar unavailable — cannot verify news blackout",
        )
    blackout_seconds = blackout_minutes * 60
    for event in events:
        delta = abs((current_time - event.event_time).total_seconds())
        if delta <= blackout_seconds:
            return GateResult.fail(
                RejectionCode.NEWS_BLACKOUT_WINDOW,
                f"{event.name} within {blackout_minutes}min blackout window",
            )
    return GateResult.ok()


# ── Gate 5 — Market regime ────────────────────────────────────────────────────

def gate_regime(
    current_regime: Regime,
    acceptable_regimes: Optional[list[Regime]] = None,
) -> GateResult:
    """Block regimes not in acceptable_regimes. Default: TRENDING and NEUTRAL pass."""
    if acceptable_regimes is None:
        acceptable_regimes = [Regime.TRENDING, Regime.NEUTRAL]
    if current_regime not in acceptable_regimes:
        if current_regime == Regime.CHOPPY:
            return GateResult.fail(RejectionCode.REGIME_CHOPPY, "regime is CHOPPY — entry blocked")
        if current_regime == Regime.UNKNOWN:
            return GateResult.fail(RejectionCode.REGIME_UNKNOWN, "regime is UNKNOWN — entry blocked")
        return GateResult.fail(
            RejectionCode.REGIME_UNKNOWN,
            f"regime {current_regime.value} not in acceptable regimes",
        )
    return GateResult.ok()


# ── Gate 6 — Portfolio state (daily loss + position exists) ───────────────────

def gate_portfolio_state(
    daily_loss: Decimal,
    order_state: OrderState,
    equity: Decimal,
    daily_loss_cap_pct: Decimal,
) -> GateResult:
    loss_cap = compute_loss_cap(equity, daily_loss_cap_pct)
    if daily_loss <= -loss_cap:
        return GateResult.fail(
            RejectionCode.DAILY_LOSS_CAP_REACHED,
            f"daily loss {daily_loss} reached cap of -{loss_cap}",
        )
    if order_state == OrderState.POSITION_OPEN:
        return GateResult.fail(RejectionCode.POSITION_EXISTS, "position already open")
    if order_state == OrderState.ORDER_PENDING:
        return GateResult.fail(RejectionCode.ORDER_IN_FLIGHT, "order already in flight")
    return GateResult.ok()


# ── Gate 7 — Position state lock ─────────────────────────────────────────────

def gate_position_state_lock(order_state: OrderState) -> GateResult:
    if order_state == OrderState.ORDER_PENDING:
        return GateResult.fail(RejectionCode.ORDER_IN_FLIGHT, "order already in flight")
    if order_state == OrderState.RECONCILING:
        return GateResult.fail(RejectionCode.SYSTEM_RECONCILING, "system is reconciling — entry blocked")
    return GateResult.ok()


# ── Gate 8 — Sequence risk ────────────────────────────────────────────────────

def gate_sequence_risk(tracker: "ConsecutiveLossTracker") -> GateResult:
    if tracker.is_in_cooldown():
        expires = tracker.cooldown_expires_at()
        return GateResult.fail(
            RejectionCode.CONSECUTIVE_LOSS_COOLDOWN,
            f"consecutive loss cooldown active — expires {expires.strftime('%Y-%m-%d %H:%M UTC') if expires else 'unknown'}",
        )
    return GateResult.ok()


# ── Gate 9 — Spread ───────────────────────────────────────────────────────────

def gate_spread(
    bid: Optional[Decimal],
    ask: Optional[Decimal],
    tick_size: Decimal,
    max_spread_ticks: int,
    mode: TradingMode,
) -> GateResult:
    if mode == TradingMode.DEV:
        return GateResult.ok()
    if bid is None or ask is None:
        return GateResult.fail(
            RejectionCode.MARKET_DATA_UNAVAILABLE,
            "market data unavailable — cannot verify spread",
        )
    current_spread = ask - bid
    max_spread = tick_size * max_spread_ticks
    if current_spread >= max_spread:
        return GateResult.fail(
            RejectionCode.SPREAD_TOO_WIDE,
            f"spread {current_spread} exceeds max {max_spread} ({max_spread_ticks} ticks)",
        )
    return GateResult.ok()


# ── Gate 10 — Signal price deviation ─────────────────────────────────────────

def gate_price_deviation(
    signal_price: Decimal,
    bid: Optional[Decimal],
    ask: Optional[Decimal],
    tick_size: Decimal,
    max_deviation_ticks: int,
    mode: TradingMode,
) -> GateResult:
    if mode == TradingMode.DEV:
        return GateResult.ok()
    if bid is None or ask is None:
        return GateResult.fail(
            RejectionCode.MARKET_DATA_UNAVAILABLE,
            "market data unavailable — cannot verify signal price deviation",
        )
    mid = (bid + ask) / 2
    deviation = abs(signal_price - mid)
    max_deviation = tick_size * max_deviation_ticks
    if deviation > max_deviation:
        return GateResult.fail(
            RejectionCode.SIGNAL_PRICE_DEVIATION,
            f"signal_price {signal_price} deviates {deviation:.4f} from market mid {mid:.4f} "
            f"(max {max_deviation} = {max_deviation_ticks} ticks)",
        )
    return GateResult.ok()


# ── Orchestrator ──────────────────────────────────────────────────────────────

def evaluate_all_gates(
    signal: "Signal",
    current_time: datetime,
    regime: Regime,
    daily_loss: Decimal,
    equity: Decimal,
    order_state: OrderState,
    bid: Optional[Decimal],
    ask: Optional[Decimal],
    events,                          # list[EconomicEvent] | None
    tracker: "ConsecutiveLossTracker",
    # session params
    expected_symbol: str,
    staleness_seconds: int,
    timezone_name: str,
    open_hour: int,
    open_minute: int,
    close_hour: int,
    close_minute: int,
    blackout_open_minutes: int,
    blackout_close_minutes: int,
    news_blackout_minutes: int,
    # risk params
    daily_loss_cap_pct: Decimal,
    # instrument params
    tick_size: Decimal,
    max_spread_ticks: int,
    max_deviation_ticks: int,
    mode: TradingMode,
    # optional
    suspended_file: Optional[Path] = None,
    allowed_directions: Optional[list[SignalAction]] = None,
    acceptable_regimes: Optional[list[Regime]] = None,
) -> GateResult:
    for check in (
        lambda: gate_suspended(suspended_file),
        lambda: gate_signal_direction(signal, allowed_directions),
        lambda: gate_signal_validity(signal, expected_symbol, staleness_seconds),
        lambda: gate_session_window(
            current_time, timezone_name,
            open_hour, open_minute, close_hour, close_minute,
            blackout_open_minutes, blackout_close_minutes,
        ),
        lambda: gate_news_blackout(current_time, events, news_blackout_minutes),
        lambda: gate_regime(regime, acceptable_regimes),
        lambda: gate_portfolio_state(daily_loss, order_state, equity, daily_loss_cap_pct),
        lambda: gate_position_state_lock(order_state),
        lambda: gate_sequence_risk(tracker),
        lambda: gate_spread(bid, ask, tick_size, max_spread_ticks, mode),
        lambda: gate_price_deviation(signal.signal_price, bid, ask, tick_size, max_deviation_ticks, mode),
    ):
        result = check()
        if not result.passed:
            return result
    return GateResult.ok()
