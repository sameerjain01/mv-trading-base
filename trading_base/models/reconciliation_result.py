from __future__ import annotations

from dataclasses import dataclass

from trading_base.constants import ReconciliationState


@dataclass(frozen=True)
class ReconciliationResult:
    state: ReconciliationState
    position_count: int = 0
    order_count: int = 0
