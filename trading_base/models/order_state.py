from __future__ import annotations

import logging
from typing import Optional

from trading_base.constants import OrderState

logger = logging.getLogger(__name__)

_LEGAL_TRANSITIONS: frozenset[tuple[OrderState, OrderState]] = frozenset({
    (OrderState.IDLE,          OrderState.ORDER_PENDING),
    (OrderState.ORDER_PENDING, OrderState.POSITION_OPEN),
    (OrderState.ORDER_PENDING, OrderState.IDLE),
    (OrderState.POSITION_OPEN, OrderState.IDLE),
    # Any state → RECONCILING, RECONCILING → IDLE
    (OrderState.IDLE,          OrderState.RECONCILING),
    (OrderState.ORDER_PENDING, OrderState.RECONCILING),
    (OrderState.POSITION_OPEN, OrderState.RECONCILING),
    (OrderState.RECONCILING,   OrderState.IDLE),
})


class InvalidStateTransitionError(Exception):
    pass


class OrderStateMachine:
    def __init__(self) -> None:
        self._state = OrderState.IDLE

    @property
    def state(self) -> OrderState:
        return self._state

    def transition(
        self,
        new_state: OrderState,
        reason: str = "",
        signal_id: Optional[str] = None,
    ) -> None:
        if (self._state, new_state) not in _LEGAL_TRANSITIONS:
            raise InvalidStateTransitionError(
                f"Illegal transition {self._state.value} → {new_state.value}"
            )
        logger.info(
            "State transition",
            extra={
                "from_state": self._state.value,
                "to_state": new_state.value,
                "reason": reason,
                "signal_id": signal_id,
            },
        )
        self._state = new_state
