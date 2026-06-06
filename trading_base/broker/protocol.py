from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from trading_base.config import InstrumentCfg
    from trading_base.models.order_record import OrderRecord
    from trading_base.models.position import PositionRecord
    from trading_base.models.reconciliation_result import ReconciliationResult
    from trading_base.models.submission_result import SubmissionResult


@runtime_checkable
class BrokerAdapter(Protocol):
    """Structural protocol — implement these methods to satisfy the interface."""

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    def is_connected(self) -> bool: ...

    async def get_account_equity(self) -> Decimal: ...

    async def get_open_positions(self, symbol: str) -> "list[PositionRecord]": ...

    async def get_open_orders(self, symbol: str) -> "list[OrderRecord]": ...

    async def submit_bracket(
        self,
        entry_price: Decimal,
        stop_price: Decimal,
        target_price: Decimal,
        quantity: int,
        instrument_cfg: "InstrumentCfg",
    ) -> "SubmissionResult": ...

    async def cancel_order(self, order_id: int) -> bool: ...

    async def close_position_market(
        self,
        symbol: str,
        quantity: int,
        instrument_cfg: "InstrumentCfg",
    ) -> "SubmissionResult": ...

    async def reconcile_on_startup(self, symbol: str) -> "ReconciliationResult": ...
