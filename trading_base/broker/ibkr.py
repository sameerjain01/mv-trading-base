from __future__ import annotations

import asyncio
import logging
import time
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING, Optional

from trading_base.constants import (
    ExecutionStatus,
    IBKROrderStatus,
    Precision,
    ReconciliationState,
    TradingMode,
)
from trading_base.models.order_record import OrderRecord
from trading_base.models.position import PositionRecord
from trading_base.models.reconciliation_result import ReconciliationResult
from trading_base.models.submission_result import SubmissionResult

if TYPE_CHECKING:
    from ib_async import IB
    from trading_base.config import IBKRCfg, InstrumentCfg

logger = logging.getLogger(__name__)

# IBKR sentinel value for unset float fields (double max)
_UNSET_DOUBLE = 1.7976931348623157e+308


class IBKRConnectionError(Exception):
    pass


class IBKRDataError(Exception):
    pass


class IBKRAdapter:
    """Async-compatible IBKR broker adapter.

    Implements BrokerAdapter protocol. All methods check mode at entry — DEV
    never calls ib_async. ib_async is imported lazily everywhere to keep DEV/test
    paths free of the ib_async import.
    """

    def __init__(
        self,
        ibkr_cfg: "IBKRCfg",
        mode: TradingMode,
        instrument_cfg: "InstrumentCfg",
    ) -> None:
        self._cfg = ibkr_cfg
        self._mode = mode
        self._instrument_cfg = instrument_cfg
        self._ib: Optional["IB"] = None

    # ── Connection ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        if self.is_connected():
            logger.debug("IBKR already connected, skipping reconnect")
            return

        if self._mode == TradingMode.DEV:
            logger.info("DEV mode: IBKR connection skipped")
            return

        port = self._cfg.port_for(self._mode)

        logger.info(
            "Connecting to IBKR Gateway",
            extra={"host": self._cfg.host, "port": port, "client_id": self._cfg.client_id},
        )

        from ib_async import IB
        ib = IB()
        try:
            await ib.connectAsync(
                self._cfg.host,
                port,
                clientId=self._cfg.client_id,
                timeout=self._cfg.connection_timeout_seconds,
            )
        except Exception as exc:
            logger.error("IBKR connection failed", extra={"error": str(exc)})
            raise IBKRConnectionError(
                f"Failed to connect to IBKR Gateway at port {port}: {exc}"
            ) from exc

        if not ib.isConnected():
            raise IBKRConnectionError(
                f"Connected to IBKR at port {port} but isConnected() returned False"
            )

        self._ib = ib
        logger.info("IBKR connection established", extra={"port": port})
        await self._prewarm_hmds()

    async def disconnect(self) -> None:
        if self._ib is not None and self._ib.isConnected():
            self._ib.disconnect()
            logger.info("IBKR disconnected")
        self._ib = None

    def is_connected(self) -> bool:
        return self._ib is not None and self._ib.isConnected()

    # ── Account ────────────────────────────────────────────────────────────────

    async def get_account_equity(self) -> Decimal:
        if self._mode == TradingMode.DEV:
            raise IBKRDataError("Cannot fetch account equity in DEV mode")
        if not self.is_connected():
            raise IBKRDataError("Cannot fetch account equity: not connected")

        for av in self._ib.accountValues():
            if av.tag == "NetLiquidation" and av.currency == self._instrument_cfg.currency:
                try:
                    equity = Decimal(av.value).quantize(Precision.IBKR_AMOUNT, ROUND_HALF_EVEN)
                except Exception as exc:
                    raise IBKRDataError(
                        f"NetLiquidation is not a valid Decimal: {av.value!r}"
                    ) from exc
                logger.info("Account equity fetched", extra={"equity": str(equity)})
                return equity.quantize(Precision.AMOUNT, ROUND_HALF_EVEN)

        raise IBKRDataError("NetLiquidation not found in IBKR account values")

    # ── Positions / orders ─────────────────────────────────────────────────────

    async def get_open_positions(self, symbol: str) -> list[PositionRecord]:
        if self._mode == TradingMode.DEV:
            raise IBKRDataError("Cannot fetch positions in DEV mode")
        if not self.is_connected():
            raise IBKRDataError("Cannot fetch positions: not connected")

        result: list[PositionRecord] = []
        for pos in self._ib.positions():
            if pos.contract.symbol != symbol:
                continue
            quantity = (
                Decimal(str(pos.position))
                .quantize(Precision.IBKR_QTY, ROUND_DOWN)
                .quantize(Precision.QTY, ROUND_DOWN)
            )
            avg_cost = (
                Decimal(str(pos.avgCost))
                .quantize(Precision.IBKR_AMOUNT, ROUND_HALF_EVEN)
                .quantize(Precision.AMOUNT, ROUND_HALF_EVEN)
            )
            result.append(PositionRecord(
                symbol=pos.contract.symbol,
                quantity=quantity,
                avg_cost=avg_cost,
                account=pos.account,
            ))

        logger.info("Open positions fetched", extra={"symbol": symbol, "count": len(result)})
        return result

    async def get_open_orders(self, symbol: str) -> list[OrderRecord]:
        if self._mode == TradingMode.DEV:
            raise IBKRDataError("Cannot fetch orders in DEV mode")
        if not self.is_connected():
            raise IBKRDataError("Cannot fetch orders: not connected")

        result: list[OrderRecord] = []
        tick = self._instrument_cfg.tick_size

        for trade in self._ib.openTrades():
            if trade.contract.symbol != symbol:
                continue

            try:
                quantity = (
                    Decimal(str(trade.order.totalQuantity))
                    .quantize(Precision.IBKR_QTY, ROUND_DOWN)
                    .quantize(Precision.QTY, ROUND_DOWN)
                )

                raw_limit = trade.order.lmtPrice
                limit_price = (
                    Decimal(str(raw_limit))
                    .quantize(tick, ROUND_HALF_EVEN)
                    .quantize(Precision.PRICE, ROUND_HALF_EVEN)
                    if raw_limit > 0 and raw_limit != _UNSET_DOUBLE
                    else None
                )

                raw_aux = trade.order.auxPrice
                aux_price = (
                    Decimal(str(raw_aux))
                    .quantize(tick, ROUND_HALF_EVEN)
                    .quantize(Precision.PRICE, ROUND_HALF_EVEN)
                    if raw_aux > 0 and raw_aux != _UNSET_DOUBLE
                    else None
                )
            except Exception as exc:
                raise IBKRDataError(
                    f"Order {trade.order.orderId} field is not a valid Decimal: {exc}"
                ) from exc

            result.append(OrderRecord(
                order_id=trade.order.orderId,
                symbol=trade.contract.symbol,
                action=trade.order.action,
                order_type=trade.order.orderType,
                quantity=quantity,
                limit_price=limit_price,
                aux_price=aux_price,
                status=trade.orderStatus.status,
            ))

        logger.info("Open orders fetched", extra={"symbol": symbol, "count": len(result)})
        return result

    # ── Execution ──────────────────────────────────────────────────────────────

    async def submit_bracket(
        self,
        entry_price: Decimal,
        stop_price: Decimal,
        target_price: Decimal,
        quantity: int,
        instrument_cfg: "InstrumentCfg",
    ) -> SubmissionResult:
        if self._mode == TradingMode.DEV:
            logger.info(
                "DEV mode: bracket submission skipped (hypothetical)",
                extra={"entry": str(entry_price), "stop": str(stop_price), "target": str(target_price)},
            )
            return SubmissionResult(status=ExecutionStatus.SUBMITTED)

        if not self.is_connected():
            return SubmissionResult(status=ExecutionStatus.REJECTED, error="not connected to IBKR")

        from trading_base.execution.bracket import build_bracket_order
        bracket = build_bracket_order(entry_price, stop_price, target_price, quantity, instrument_cfg)

        entry_id = self._ib.client.getReqId()
        stop_id = self._ib.client.getReqId()
        target_id = self._ib.client.getReqId()
        bracket.entry.orderId = entry_id
        bracket.stop.parentId = entry_id
        bracket.stop.orderId = stop_id
        bracket.target.parentId = entry_id
        bracket.target.orderId = target_id
        bracket.target.transmit = True

        logger.info(
            "Submitting bracket order",
            extra={"entry_id": entry_id, "entry_price": str(entry_price)},
        )

        try:
            contract = self._build_contract(instrument_cfg)
            if not contract.conId:
                await self._ib.qualifyContractsAsync(contract)
            if not contract.conId:
                raise RuntimeError(
                    f"Contract {contract} not resolved by IBKR — conId still 0 after qualify"
                )
            entry_trade = self._ib.placeOrder(contract, bracket.entry)
            stop_trade = self._ib.placeOrder(contract, bracket.stop)
            target_trade = self._ib.placeOrder(contract, bracket.target)
        except Exception as exc:
            logger.error("Bracket submission failed", extra={"error": str(exc)})
            return SubmissionResult(status=ExecutionStatus.REJECTED, error=str(exc))

        result = SubmissionResult(
            status=ExecutionStatus.SUBMITTED,
            entry_order_id=entry_trade.order.orderId,
            stop_order_id=stop_trade.order.orderId,
            target_order_id=target_trade.order.orderId,
        )
        logger.info(
            "Bracket submission accepted",
            extra={
                "entry_order_id": result.entry_order_id,
                "stop_order_id": result.stop_order_id,
                "target_order_id": result.target_order_id,
            },
        )
        return result

    async def cancel_order(self, order_id: int) -> bool:
        if self._mode == TradingMode.DEV:
            logger.info("DEV mode: order cancellation skipped", extra={"order_id": order_id})
            return True
        if not self.is_connected():
            return False

        trade = next(
            (t for t in self._ib.openTrades() if t.order.orderId == order_id), None
        )
        if trade is None:
            logger.warning("cancel_order: order not found", extra={"order_id": order_id})
            return False

        try:
            self._ib.cancelOrder(trade.order)
        except Exception as exc:
            logger.error("Order cancellation failed", extra={"order_id": order_id, "error": str(exc)})
            return False

        logger.info("Order cancellation sent", extra={"order_id": order_id})
        return True

    async def close_position_market(
        self,
        symbol: str,
        quantity: int,
        instrument_cfg: "InstrumentCfg",
    ) -> SubmissionResult:
        logger.critical(
            "Emergency market close initiated",
            extra={"symbol": symbol, "quantity": quantity, "mode": self._mode.value},
        )

        if self._mode == TradingMode.DEV:
            logger.critical("DEV mode: emergency market close skipped (hypothetical)")
            return SubmissionResult(status=ExecutionStatus.SUBMITTED)

        if not self.is_connected():
            return SubmissionResult(status=ExecutionStatus.REJECTED, error="not connected to IBKR")

        from ib_async import MarketOrder
        from trading_base.constants import SignalAction
        order = MarketOrder(action=SignalAction.SELL.value, totalQuantity=quantity)

        try:
            contract = self._build_contract(instrument_cfg)
            trade = self._ib.placeOrder(contract, order)
        except Exception as exc:
            logger.error("Emergency close failed", extra={"error": str(exc)})
            return SubmissionResult(status=ExecutionStatus.REJECTED, error=str(exc))

        result = SubmissionResult(status=ExecutionStatus.SUBMITTED, entry_order_id=trade.order.orderId)
        logger.critical("Emergency market close submitted", extra={"order_id": result.entry_order_id})
        return result

    async def reconcile_on_startup(self, symbol: str) -> ReconciliationResult:
        if self._mode == TradingMode.DEV:
            logger.info("DEV mode: startup reconciliation skipped")
            return ReconciliationResult(state=ReconciliationState.NO_POSITION)

        if not self.is_connected():
            return ReconciliationResult(state=ReconciliationState.UNKNOWN)

        await self._ib.reqAllOpenOrdersAsync()
        await asyncio.sleep(1)

        try:
            positions = await self.get_open_positions(symbol)
            orders = await self.get_open_orders(symbol)
        except Exception as exc:
            logger.error("reconcile_on_startup: failed", extra={"error": str(exc)})
            return ReconciliationResult(state=ReconciliationState.UNKNOWN)

        if not positions:
            state = ReconciliationState.NO_POSITION
        elif orders:
            state = ReconciliationState.POSITION_WITH_BRACKET
        else:
            state = ReconciliationState.POSITION_WITHOUT_BRACKET

        logger.info("Startup reconciliation state", extra={"state": state.value})
        return ReconciliationResult(
            state=state,
            position_count=len(positions),
            order_count=len(orders),
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def confirm_bracket_active(self, order_ids: list[int], timeout_seconds: int) -> bool:
        if self._mode == TradingMode.DEV:
            logger.info("DEV mode: bracket confirmation skipped (hypothetical active)")
            return True
        if not order_ids or not self.is_connected():
            return False

        active = frozenset({IBKROrderStatus.SUBMITTED, IBKROrderStatus.PRE_SUBMITTED})
        ids_set = set(order_ids)
        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            confirmed = {
                t.order.orderId
                for t in self._ib.openTrades()
                if t.order.orderId in ids_set and t.orderStatus.status in active
            }
            if confirmed == ids_set:
                return True
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(1.0, remaining))

        logger.warning("Bracket confirmation timed out", extra={"order_ids": order_ids})
        return False

    def wait_for_entry_fill(self, order_id: int, timeout_seconds: int) -> tuple[bool, Optional[Decimal]]:
        if self._mode == TradingMode.DEV:
            return True, Decimal("0")
        if not self.is_connected():
            return False, None

        deadline = time.monotonic() + timeout_seconds
        tick = self._instrument_cfg.tick_size

        while time.monotonic() < deadline:
            for trade in self._ib.trades():
                if (
                    trade.order.orderId == order_id
                    and trade.orderStatus.status == IBKROrderStatus.FILLED.value
                ):
                    fill_price = (
                        Decimal(str(trade.orderStatus.avgFillPrice))
                        .quantize(tick, ROUND_HALF_EVEN)
                        .quantize(Precision.PRICE, ROUND_HALF_EVEN)
                    )
                    logger.info("Entry fill confirmed", extra={"fill_price": str(fill_price)})
                    return True, fill_price
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(1.0, remaining))

        logger.warning("Entry fill timeout", extra={"order_id": order_id})
        return False, None

    async def _prewarm_hmds(self) -> None:
        if self._ib is None:
            return
        contract = self._build_contract(self._instrument_cfg)
        try:
            bars = await self._ib.reqHistoricalDataAsync(
                contract,
                endDateTime="",
                durationStr="120 S",
                barSizeSetting="1 min",
                whatToShow="MIDPOINT",
                useRTH=False,
                timeout=15,
            )
            mid = Decimal(str(bars[-1].close)) if bars else None
            logger.info("HMDS pre-warm complete", extra={"bars": len(bars), "mid": str(mid) if mid else "none"})
        except Exception as exc:
            logger.warning("HMDS pre-warm failed", extra={"error": str(exc)})

    @staticmethod
    def _build_contract(instrument_cfg: "InstrumentCfg"):
        """Build ib_async contract from InstrumentCfg. Supports STOCK, FUTURES, OPTION."""
        itype = instrument_cfg.instrument_type.upper()
        if itype == "FUTURES":
            from ib_async import Future
            c = Future()
            c.symbol = instrument_cfg.symbol
            c.exchange = instrument_cfg.exchange
            c.currency = instrument_cfg.currency
            return c
        if itype == "STOCK":
            from ib_async import Stock
            return Stock(instrument_cfg.symbol, instrument_cfg.exchange, instrument_cfg.currency)
        if itype == "OPTION":
            from ib_async import Option
            return Option(instrument_cfg.symbol, exchange=instrument_cfg.exchange, currency=instrument_cfg.currency)
        raise ValueError(f"Unsupported instrument_type: {instrument_cfg.instrument_type!r}")
