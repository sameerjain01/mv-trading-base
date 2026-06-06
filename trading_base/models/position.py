from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PositionRecord:
    symbol: str
    quantity: Decimal
    avg_cost: Decimal
    account: str
