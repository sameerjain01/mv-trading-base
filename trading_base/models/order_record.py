from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class OrderRecord:
    order_id: int
    symbol: str
    action: str
    order_type: str
    quantity: Decimal
    limit_price: Optional[Decimal]
    aux_price: Optional[Decimal]
    status: str
