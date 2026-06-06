import uuid
from decimal import Decimal
from enum import Enum


class OrderState(str, Enum):
    IDLE          = "IDLE"
    ORDER_PENDING = "ORDER_PENDING"
    POSITION_OPEN = "POSITION_OPEN"
    RECONCILING   = "RECONCILING"


class Regime(str, Enum):
    TRENDING = "TRENDING"
    NEUTRAL  = "NEUTRAL"
    CHOPPY   = "CHOPPY"
    UNKNOWN  = "REGIME_UNKNOWN"


class RejectionCode(str, Enum):
    INVALID_SIGNAL_STRUCTURE   = "INVALID_SIGNAL_STRUCTURE"
    OUTSIDE_SESSION_WINDOW     = "OUTSIDE_SESSION_WINDOW"
    NEWS_BLACKOUT_WINDOW       = "NEWS_BLACKOUT_WINDOW"
    REGIME_CHOPPY              = "REGIME_CHOPPY"
    REGIME_UNKNOWN             = "REJECT_REGIME_UNKNOWN"
    REGIME_OVERRIDE_HIGH_VIX   = "REGIME_OVERRIDE_HIGH_VIX"
    DAILY_LOSS_CAP_REACHED     = "DAILY_LOSS_CAP_REACHED"
    POSITION_EXISTS            = "POSITION_EXISTS"
    CONSECUTIVE_LOSS_COOLDOWN  = "CONSECUTIVE_LOSS_COOLDOWN"
    SPREAD_TOO_WIDE            = "SPREAD_TOO_WIDE"
    MARKET_CLOSED              = "MARKET_CLOSED"
    ORDER_IN_FLIGHT            = "ORDER_IN_FLIGHT"
    SYSTEM_RECONCILING         = "SYSTEM_RECONCILING"
    SELL_SIGNAL_NO_SHORT_V1    = "SELL_SIGNAL_NO_SHORT_V1"
    STOP_DISTANCE_OUT_OF_RANGE = "STOP_DISTANCE_OUT_OF_RANGE"
    INSUFFICIENT_CONTRACTS     = "INSUFFICIENT_CONTRACTS"
    IBKR_REJECTION             = "IBKR_REJECTION"
    ENTRY_TIMEOUT              = "ENTRY_TIMEOUT"
    BRACKET_FAILURE            = "REJECT_BRACKET_FAILURE"
    CALENDAR_API_UNAVAILABLE   = "CALENDAR_API_UNAVAILABLE"
    EDGE_DEGRADATION_SUSPENSION = "EDGE_DEGRADATION_SUSPENSION"
    SYSTEM_SUSPENDED           = "SYSTEM_SUSPENDED"
    HEALTH_CHECK               = "HEALTH_CHECK"
    SIGNAL_PRICE_DEVIATION     = "SIGNAL_PRICE_DEVIATION"
    MARKET_DATA_UNAVAILABLE    = "MARKET_DATA_UNAVAILABLE"


class ExitReason(str, Enum):
    STOP_LOSS       = "STOP_LOSS"
    TAKE_PROFIT     = "TAKE_PROFIT"
    SESSION_END     = "SESSION_END"
    BRACKET_FAILURE = "EXIT_BRACKET_FAILURE"
    KILL_SWITCH     = "KILL_SWITCH"
    OPEN            = "OPEN"
    UNKNOWN         = "EXIT_UNKNOWN"


class SignalAction(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"


class HypotheticalOutcome(str, Enum):
    WIN     = "WIN"
    LOSS    = "LOSS"
    UNKNOWN = "OUTCOME_UNKNOWN"


class TradingMode(str, Enum):
    DEV   = "dev"
    PAPER = "paper"
    LIVE  = "live"


class OrderTIF(str, Enum):
    DAY = "DAY"
    GTC = "GTC"


class ExecutionStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    FILLED    = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED  = "REJECTED"
    TIMEOUT   = "TIMEOUT"


class IBKROrderStatus(str, Enum):
    SUBMITTED     = "Submitted"
    PRE_SUBMITTED = "PreSubmitted"
    FILLED        = "Filled"
    CANCELLED     = "Cancelled"
    INACTIVE      = "Inactive"


class ReconciliationState(str, Enum):
    NO_POSITION              = "NO_POSITION"
    POSITION_WITH_BRACKET    = "POSITION_WITH_BRACKET"
    POSITION_WITHOUT_BRACKET = "POSITION_WITHOUT_BRACKET"
    UNKNOWN                  = "RECONCILIATION_UNKNOWN"


class DegradationLevel(str, Enum):
    NONE       = "NONE"
    WARNING    = "WARNING"
    REDUCTION  = "REDUCTION"
    SUSPENSION = "SUSPENSION"


class Precision:
    # Internal storage / calculation
    PRICE  = Decimal("0.0001")
    QTY    = Decimal("0.000001")
    AMOUNT = Decimal("0.0001")
    RATE   = Decimal("0.000001")

    # IBKR broker boundary — instrument-specific; callers set from InstrumentCfg
    IBKR_QTY    = Decimal("1")
    IBKR_AMOUNT = Decimal("0.01")


class HighImpactEvent:
    KEYWORDS: frozenset = frozenset({
        "FOMC",
        "Federal Reserve",
        "Non-Farm Payrolls",
        "NFP",
        "CPI",
        "GDP",
        "PPI",
        "Unemployment Rate",
        "Retail Sales",
        "ISM Manufacturing",
        "ISM Services",
        "Fed Chair",
        "Interest Rate Decision",
    })


HEALTH_CHECK_STRATEGY: str = "HEALTH_CHECK"


def new_trade_id() -> str:
    return str(uuid.uuid4())

def new_rejection_id() -> str:
    return str(uuid.uuid4())

def new_signal_id() -> str:
    return str(uuid.uuid4())
