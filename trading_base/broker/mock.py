from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional, TYPE_CHECKING

from trading_base.constants import ExecutionStatus, ReconciliationState
from trading_base.models.reconciliation_result import ReconciliationResult
from trading_base.models.submission_result import SubmissionResult

if TYPE_CHECKING:
    from trading_base.config import InstrumentCfg
    from trading_base.models.order_record import OrderRecord
    from trading_base.models.position import PositionRecord

logger = logging.getLogger(__name__)


class MockBrokerAdapter:
    """In-process mock — satisfies BrokerAdapter protocol. Used in all non-IBKR tests.

    Pass `responses` to control return values or raise exceptions:
        mock = MockBrokerAdapter({
            'get_account_equity': Decimal('50000'),
            'submit_bracket': SubmissionResult(status=ExecutionStatus.SUBMITTED),
        })
    Unspecified methods return sensible defaults. Pass an Exception instance to
    have the method raise it:
        mock = MockBrokerAdapter({'get_account_equity': ValueError("unavailable")})
    """

    def __init__(self, responses: Optional[dict[str, Any]] = None) -> None:
        self._responses: dict[str, Any] = responses or {}
        self._connected = False
        self.calls: dict[str, list[tuple]] = {}

    # ── Recording ─────────────────────────────────────────────────────────────

    def _record(self, method: str, *args) -> None:
        self.calls.setdefault(method, []).append(args)

    def _resolve(self, method: str, default: Any) -> Any:
        if method not in self._responses:
            return default
        value = self._responses[method]
        if isinstance(value, BaseException):
            raise value
        return value

    # ── Protocol implementation ────────────────────────────────────────────────

    async def connect(self) -> None:
        self._record("connect")
        self._connected = True
        logger.debug("MockBrokerAdapter: connect()")

    async def disconnect(self) -> None:
        self._record("disconnect")
        self._connected = False
        logger.debug("MockBrokerAdapter: disconnect()")

    def is_connected(self) -> bool:
        self._record("is_connected")
        return self._resolve("is_connected", self._connected)

    async def get_account_equity(self) -> Decimal:
        self._record("get_account_equity")
        return self._resolve("get_account_equity", Decimal("50000"))

    async def get_open_positions(self, symbol: str) -> "list[PositionRecord]":
        self._record("get_open_positions", symbol)
        return self._resolve("get_open_positions", [])

    async def get_open_orders(self, symbol: str) -> "list[OrderRecord]":
        self._record("get_open_orders", symbol)
        return self._resolve("get_open_orders", [])

    async def submit_bracket(
        self,
        entry_price: Decimal,
        stop_price: Decimal,
        target_price: Decimal,
        quantity: int,
        instrument_cfg: "InstrumentCfg",
    ) -> SubmissionResult:
        self._record("submit_bracket", entry_price, stop_price, target_price, quantity)
        return self._resolve(
            "submit_bracket",
            SubmissionResult(
                status=ExecutionStatus.SUBMITTED,
                entry_order_id=1001,
                stop_order_id=1002,
                target_order_id=1003,
            ),
        )

    async def cancel_order(self, order_id: int) -> bool:
        self._record("cancel_order", order_id)
        return self._resolve("cancel_order", True)

    async def close_position_market(
        self,
        symbol: str,
        quantity: int,
        instrument_cfg: "InstrumentCfg",
    ) -> SubmissionResult:
        self._record("close_position_market", symbol, quantity)
        return self._resolve(
            "close_position_market",
            SubmissionResult(status=ExecutionStatus.SUBMITTED, entry_order_id=9999),
        )

    async def reconcile_on_startup(self, symbol: str) -> ReconciliationResult:
        self._record("reconcile_on_startup", symbol)
        return self._resolve(
            "reconcile_on_startup",
            ReconciliationResult(state=ReconciliationState.NO_POSITION),
        )
