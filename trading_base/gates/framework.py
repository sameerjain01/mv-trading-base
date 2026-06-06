from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from trading_base.constants import RejectionCode


@dataclass(frozen=True)
class GateResult:
    passed: bool
    rejection_code: Optional[RejectionCode] = None
    reason: Optional[str] = None

    @classmethod
    def ok(cls) -> "GateResult":
        return cls(passed=True)

    @classmethod
    def fail(cls, code: RejectionCode, reason: str) -> "GateResult":
        return cls(passed=False, rejection_code=code, reason=reason)
