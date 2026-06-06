from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

from trading_base.constants import Precision, SignalAction, new_signal_id

logger = logging.getLogger(__name__)


class InvalidSignalError(Exception):
    pass


@dataclass(frozen=True)
class Signal:
    signal_id: str
    symbol: str
    action: SignalAction
    strategy: str
    timeframe: str
    timestamp_received: datetime
    timestamp_signal: datetime
    signal_price: Decimal
    stop_price: Decimal
    secret_hash: str
    raw_payload: MappingProxyType = field(hash=False, compare=False)

    def validate_hmac(self, secret: str) -> bool:
        """Return True if sha256(secret) matches the stored secret_hash."""
        import hmac as _hmac
        expected = hashlib.sha256(secret.encode()).hexdigest()
        return _hmac.compare_digest(self.secret_hash, expected)

    @classmethod
    def from_webhook_payload(
        cls,
        payload: dict,
        *,
        expected_symbol: str | None = None,
        staleness_seconds: int = 300,
    ) -> "Signal":
        now = datetime.now(timezone.utc)

        symbol = payload.get("symbol")
        if not symbol:
            raise InvalidSignalError("Missing required field: symbol")
        if expected_symbol and symbol != expected_symbol:
            raise InvalidSignalError(
                f"Invalid symbol: {symbol!r}; expected {expected_symbol!r}"
            )

        raw_action = payload.get("action")
        if not raw_action:
            raise InvalidSignalError("Missing required field: action")
        try:
            action = SignalAction(raw_action)
        except ValueError:
            raise InvalidSignalError(f"Invalid action: {raw_action!r}; expected BUY or SELL")

        strategy = payload.get("strategy")
        if not strategy:
            raise InvalidSignalError("Missing required field: strategy")

        timeframe = payload.get("timeframe")
        if not timeframe:
            raise InvalidSignalError("Missing required field: timeframe")

        raw_ts = payload.get("timestamp")
        if raw_ts is None:
            raise InvalidSignalError("Missing required field: timestamp")
        timestamp_signal = _parse_timestamp(raw_ts)

        age_seconds = (now - timestamp_signal).total_seconds()
        if not (0 <= age_seconds <= staleness_seconds):
            raise InvalidSignalError(
                f"Signal timestamp invalid: {age_seconds:.0f}s old (limit {staleness_seconds}s)"
            )

        raw_price = payload.get("signal_price")
        if raw_price is None:
            raise InvalidSignalError("Missing required field: signal_price")
        signal_price = _parse_decimal("signal_price", raw_price)
        if signal_price <= 0:
            raise InvalidSignalError(f"signal_price must be positive: {signal_price}")

        raw_stop = payload.get("stop_price")
        if raw_stop is None:
            raise InvalidSignalError("Missing required field: stop_price")
        stop_price = _parse_decimal("stop_price", raw_stop)
        if stop_price <= 0:
            raise InvalidSignalError(f"stop_price must be positive: {stop_price}")

        if action == SignalAction.BUY and stop_price >= signal_price:
            raise InvalidSignalError(
                f"stop_price ({stop_price}) must be below signal_price ({signal_price}) for BUY"
            )

        raw_secret = payload.get("secret")
        if not isinstance(raw_secret, str):
            raise InvalidSignalError("Missing required field: secret (must be a string)")
        secret_hash = hashlib.sha256(raw_secret.encode()).hexdigest()

        client_signal_id = payload.get("signal_id")
        signal_id = new_signal_id()
        if client_signal_id:
            logger.debug(
                "Client-provided signal_id ignored; server-generated id used",
                extra={"client_signal_id": client_signal_id, "server_signal_id": signal_id},
            )

        sanitized = MappingProxyType({k: v for k, v in payload.items() if k != "secret"})

        return cls(
            signal_id=signal_id,
            symbol=symbol,
            action=action,
            strategy=strategy,
            timeframe=timeframe,
            timestamp_received=now,
            timestamp_signal=timestamp_signal,
            signal_price=signal_price,
            stop_price=stop_price,
            secret_hash=secret_hash,
            raw_payload=sanitized,
        )


def _parse_decimal(field_name: str, raw) -> Decimal:
    try:
        return Decimal(str(raw)).quantize(Precision.PRICE)
    except (InvalidOperation, ValueError):
        raise InvalidSignalError(f"Invalid {field_name}: {raw!r}")


def _parse_timestamp(raw) -> datetime:
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except ValueError:
            pass
    raise InvalidSignalError(f"Cannot parse timestamp: {raw!r}")
