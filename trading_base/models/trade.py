from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from types import MappingProxyType

from trading_base.constants import ExitReason, Regime, SignalAction

JOURNAL_FIELDS: tuple[str, ...] = (
    "trade_id",
    "timestamp_signal",
    "timestamp_entry",
    "timestamp_exit",
    "direction",
    "entry_price",
    "stop_price",
    "target_price",
    "stop_distance_points",
    "target_distance_points",
    "rr_ratio",
    "quantity",
    "support_level",
    "resistance_level",
    "regime_at_entry",
    "vix_at_entry",
    "market_context",
    "filters_fired",
    "exit_reason",
    "exit_price",
    "gross_pnl",
    "commission",
    "slippage_applied",
    "net_pnl",
    "assumption",
    "outcome_note",
    # options fields (None when not applicable)
    "expiry",
    "strike",
    "put_call",
    "delta",
)


@dataclass(frozen=True)
class Trade:
    trade_id: str
    timestamp_signal: datetime
    timestamp_entry: datetime
    timestamp_exit: datetime
    direction: SignalAction
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    stop_distance_points: Decimal
    target_distance_points: Decimal
    rr_ratio: Decimal
    quantity: int                           # renamed from contracts
    support_level: Decimal
    resistance_level: Decimal
    regime_at_entry: Regime
    vix_at_entry: Decimal
    market_context: str                     # generic; strategy fills (e.g. "ABOVE_20MA")
    filters_fired: MappingProxyType[str, bool]
    exit_reason: ExitReason
    exit_price: Decimal
    gross_pnl: Decimal
    commission: Decimal
    slippage_applied: Decimal
    net_pnl: Decimal
    assumption: str
    outcome_note: str
    # options-specific (None for futures/equities)
    expiry: Optional[date] = None
    strike: Optional[Decimal] = None
    put_call: Optional[str] = None
    delta: Optional[Decimal] = None

    def __post_init__(self) -> None:
        for name, value in (
            ("timestamp_signal", self.timestamp_signal),
            ("timestamp_entry", self.timestamp_entry),
            ("timestamp_exit", self.timestamp_exit),
        ):
            if value.tzinfo is None:
                raise ValueError(f"Trade.{name} must be timezone-aware, got: {value!r}")

    def to_dict(self) -> dict[str, object]:
        return {
            "trade_id": self.trade_id,
            "timestamp_signal": self.timestamp_signal.isoformat(),
            "timestamp_entry": self.timestamp_entry.isoformat(),
            "timestamp_exit": self.timestamp_exit.isoformat(),
            "direction": self.direction.value,
            "entry_price": str(self.entry_price),
            "stop_price": str(self.stop_price),
            "target_price": str(self.target_price),
            "stop_distance_points": str(self.stop_distance_points),
            "target_distance_points": str(self.target_distance_points),
            "rr_ratio": str(self.rr_ratio),
            "quantity": self.quantity,
            "support_level": str(self.support_level),
            "resistance_level": str(self.resistance_level),
            "regime_at_entry": self.regime_at_entry.value,
            "vix_at_entry": str(self.vix_at_entry),
            "market_context": self.market_context,
            "filters_fired": json.dumps(dict(self.filters_fired)),
            "exit_reason": self.exit_reason.value,
            "exit_price": str(self.exit_price),
            "gross_pnl": str(self.gross_pnl),
            "commission": str(self.commission),
            "slippage_applied": str(self.slippage_applied),
            "net_pnl": str(self.net_pnl),
            "assumption": self.assumption,
            "outcome_note": self.outcome_note,
            "expiry": self.expiry.isoformat() if self.expiry is not None else None,
            "strike": str(self.strike) if self.strike is not None else None,
            "put_call": self.put_call,
            "delta": str(self.delta) if self.delta is not None else None,
        }

    def to_csv_row(self) -> list[object]:
        d = self.to_dict()
        return [d[f] for f in JOURNAL_FIELDS]
