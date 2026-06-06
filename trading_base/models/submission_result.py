from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from trading_base.constants import ExecutionStatus


@dataclass(frozen=True)
class SubmissionResult:
    status: ExecutionStatus
    entry_order_id: Optional[int] = None
    stop_order_id: Optional[int] = None
    target_order_id: Optional[int] = None
    error: Optional[str] = None
