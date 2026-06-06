from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trading_base.config import InstrumentCfg

from trading_base.constants import OrderTIF, Precision, SignalAction


class InvalidOrderError(Exception):
    pass


OCA_CANCEL = 1  # IBKR OCA type 1: cancel all remaining orders when one fills


@dataclass(frozen=True)
class BracketOrder:
    entry: object    # ib_async LimitOrder
    stop: object     # ib_async StopOrder
    target: object   # ib_async LimitOrder
    oca_group: str


def build_bracket_order(
    entry_price: Decimal,
    stop_price: Decimal,
    target_price: Decimal,
    quantity: int,
    instrument_cfg: "InstrumentCfg",
) -> BracketOrder:
    if quantity < 1:
        raise InvalidOrderError(f"quantity must be >= 1, got {quantity}")
    if stop_price >= entry_price:
        raise InvalidOrderError(
            f"stop_price {stop_price} must be below entry_price {entry_price} for a long"
        )
    if target_price <= entry_price:
        raise InvalidOrderError(
            f"target_price {target_price} must be above entry_price {entry_price} for a long"
        )

    entry_lmt = _quantize_to_tick(entry_price, instrument_cfg.tick_size)
    stop_lmt = _quantize_to_tick(stop_price, instrument_cfg.tick_size)
    target_lmt = _quantize_to_tick(target_price, instrument_cfg.tick_size)
    qty = Decimal(quantity).quantize(Precision.IBKR_QTY)
    oca_group = str(uuid.uuid4())

    from ib_async import LimitOrder, StopOrder  # lazy — keeps non-IBKR paths free

    entry_order = LimitOrder(
        action=SignalAction.BUY.value,
        totalQuantity=qty,
        lmtPrice=float(entry_lmt),  # float required by ib_async Order API — Decimal quantized to tick before conversion
        transmit=False,
    )

    stop_order = StopOrder(
        action=SignalAction.SELL.value,
        totalQuantity=qty,
        stopPrice=float(stop_lmt),  # float required by ib_async Order API — Decimal quantized to tick before conversion
        tif=OrderTIF.GTC.value,
        ocaGroup=oca_group,
        ocaType=OCA_CANCEL,
        transmit=False,
    )

    target_order = LimitOrder(
        action=SignalAction.SELL.value,
        totalQuantity=qty,
        lmtPrice=float(target_lmt),  # float required by ib_async Order API — Decimal quantized to tick before conversion
        tif=OrderTIF.GTC.value,
        ocaGroup=oca_group,
        ocaType=OCA_CANCEL,
    )

    return BracketOrder(
        entry=entry_order,
        stop=stop_order,
        target=target_order,
        oca_group=oca_group,
    )


def _quantize_to_tick(price: Decimal, tick_size: Decimal) -> Decimal:
    return (price / tick_size).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN) * tick_size
