from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from trading_base.constants import HypotheticalOutcome, Regime, RejectionCode, SignalAction

REJECTION_FIELDS: tuple[str, ...] = (
    "rejection_id",
    "timestamp",
    "signal_id",
    "symbol",
    "action",
    "signal_price",
    "stop_price",
    "rejection_code",
    "rejection_reason",
    "regime_at_rejection",
    "hypothetical_outcome",
    "hypothetical_pnl",
)


@dataclass(frozen=True)
class Rejection:
    rejection_id: str
    timestamp: datetime
    signal_id: str
    symbol: str
    action: SignalAction
    signal_price: Decimal
    stop_price: Decimal
    rejection_code: RejectionCode
    rejection_reason: str
    regime_at_rejection: Regime
    hypothetical_outcome: Optional[HypotheticalOutcome] = None
    hypothetical_pnl: Optional[Decimal] = None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError(f"Rejection.timestamp must be timezone-aware, got: {self.timestamp!r}")

    def to_dict(self) -> dict[str, object]:
        return {
            "rejection_id": self.rejection_id,
            "timestamp": self.timestamp.isoformat(),
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "action": self.action.value,
            "signal_price": str(self.signal_price),
            "stop_price": str(self.stop_price),
            "rejection_code": self.rejection_code.value,
            "rejection_reason": self.rejection_reason,
            "regime_at_rejection": self.regime_at_rejection.value,
            "hypothetical_outcome": (
                self.hypothetical_outcome.value if self.hypothetical_outcome is not None else None
            ),
            "hypothetical_pnl": (
                str(self.hypothetical_pnl) if self.hypothetical_pnl is not None else None
            ),
        }

    def to_csv_row(self) -> list[object]:
        d = self.to_dict()
        return [d[f] for f in REJECTION_FIELDS]
