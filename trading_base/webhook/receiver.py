from __future__ import annotations

import hashlib
import hmac
import io
import logging
import os
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from trading_base.constants import RejectionCode
from trading_base.models.signal import InvalidSignalError, Signal

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    broker_connected: bool
    order_state: str
    daily_pnl: str
    regime: str
    session_active: bool


def create_app(
    signal_handler: Optional[Callable] = None,
    broker=None,
    journal_path: Optional[Path] = None,
    expected_symbol: Optional[str] = None,
) -> FastAPI:
    """Create and return the FastAPI application.

    Args:
        signal_handler: async callable(signal: Signal) → ProcessingResult | None
        broker:         BrokerAdapter instance (for health/killswitch)
        journal_path:   Path to SQLite journal database
        expected_symbol: symbol string for signal validation (e.g. "MES")
    """
    app = FastAPI()

    _state: dict = {
        "signal_handler": signal_handler,
        "broker": broker,
        "journal_path": journal_path,
        "expected_symbol": expected_symbol,
        "kill_switch_active": False,
        "state_machine": None,
        "daily_loss_tracker": None,
        "current_regime": None,
        "last_signal_ts": None,
    }

    # ── Secret helpers ─────────────────────────────────────────────────────────

    def _validate_secret(payload: dict) -> bool:
        raw = payload.get("secret")
        if not isinstance(raw, str):
            return False
        expected = os.environ.get("WEBHOOK_SECRET", "")
        if not expected:
            return False
        return hmac.compare_digest(
            hashlib.sha256(raw.encode()).hexdigest(),
            hashlib.sha256(expected.encode()).hexdigest(),
        )

    def _validate_bearer(token: str) -> bool:
        expected = os.environ.get("WEBHOOK_SECRET", "")
        if not expected or not token:
            return False
        return hmac.compare_digest(
            hashlib.sha256(token.encode()).hexdigest(),
            hashlib.sha256(expected.encode()).hexdigest(),
        )

    # ── Health ─────────────────────────────────────────────────────────────────

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        b = _state["broker"]
        broker_connected = bool(b and b.is_connected())
        sm = _state["state_machine"]
        order_state = sm.state.value if sm else "UNKNOWN"
        dlt = _state["daily_loss_tracker"]
        daily_pnl = str(dlt.get_daily_pnl()) if dlt else "0"
        regime_obj = _state["current_regime"]
        from trading_base.constants import Regime
        regime = regime_obj.value if regime_obj else Regime.UNKNOWN.value

        return HealthResponse(
            status="ok",
            timestamp=datetime.now(timezone.utc).isoformat(),
            broker_connected=broker_connected,
            order_state=order_state,
            daily_pnl=daily_pnl,
            regime=regime,
            session_active=True,  # strategies override this by wiring their own health logic
        )

    # ── Signal ─────────────────────────────────────────────────────────────────

    @app.post("/signal")
    async def receive_signal(request: Request) -> JSONResponse:
        if _state["kill_switch_active"]:
            logger.warning("Signal rejected: kill switch is active")
            return JSONResponse(status_code=503, content={"error": "kill switch active"})

        try:
            payload = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"error": "invalid json"})

        if not _validate_secret(payload):
            logger.warning("Secret validation failed on /signal")
            return JSONResponse(status_code=401, content={"error": "unauthorized"})

        try:
            signal = Signal.from_webhook_payload(
                payload, expected_symbol=_state.get("expected_symbol")
            )
        except InvalidSignalError as exc:
            logger.warning("Signal parse failed: %s", exc)
            return JSONResponse(status_code=400, content={"error": "invalid payload"})

        _state["last_signal_ts"] = datetime.now(timezone.utc)

        handler = _state["signal_handler"]
        if handler is None:
            logger.info("Signal accepted (no handler): signal_id=%s", signal.signal_id)
            return JSONResponse(
                status_code=200,
                content={"status": "accepted", "signal_id": signal.signal_id},
            )

        result = await handler(signal)

        if result is None or getattr(result, "accepted", False):
            trade_id = getattr(result, "trade_id", None)
            return JSONResponse(
                status_code=200,
                content={"status": "accepted", "signal_id": signal.signal_id, "trade_id": trade_id},
            )

        rejection_code = getattr(result, "rejection_code", None)
        if rejection_code == RejectionCode.HEALTH_CHECK:
            b = _state["broker"]
            return JSONResponse(
                status_code=200,
                content={
                    "status": "health_check",
                    "signal_id": signal.signal_id,
                    "broker_connected": bool(b and b.is_connected()),
                    "gate": getattr(result, "reason", "unknown"),
                },
            )

        return JSONResponse(
            status_code=200,
            content={
                "status": "rejected",
                "signal_id": signal.signal_id,
                "code": rejection_code.value if rejection_code else "unknown",
            },
        )

    # ── Kill switch ────────────────────────────────────────────────────────────

    @app.post("/killswitch")
    async def killswitch(request: Request) -> JSONResponse:
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        if not _validate_bearer(token):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})

        _state["kill_switch_active"] = True
        logger.critical("KILL_SWITCH_ACTIVATED")

        b = _state["broker"]
        if b and b.is_connected():
            try:
                orders = await b.get_open_orders(_state.get("expected_symbol") or "")
                for order in orders:
                    await b.cancel_order(order.order_id)
            except Exception as exc:
                logger.error("Kill switch: cancel orders failed: %s", exc)
            try:
                if _state.get("expected_symbol"):
                    from trading_base.broker.ibkr import IBKRAdapter
                    if isinstance(b, IBKRAdapter):
                        await b.close_position_market(
                            _state["expected_symbol"], 1, b._instrument_cfg
                        )
            except Exception as exc:
                logger.error("Kill switch: close position failed: %s", exc)

        from trading_base.logging import send_alert
        send_alert("KILL_SWITCH_ACTIVATED by operator", "CRITICAL")

        return JSONResponse(status_code=200, content={"status": "kill_switch_activated"})

    # ── Journal exports ────────────────────────────────────────────────────────

    @app.get("/journal/trades")
    async def journal_trades(date: Optional[str] = Query(None)) -> PlainTextResponse:
        from trading_base.journal.export import export_trades_csv
        jp = _state["journal_path"]
        if jp is None:
            return PlainTextResponse("db not initialized", status_code=503)
        filter_date = _parse_date(date)
        csv_str = export_trades_csv(jp, date_from=filter_date, date_to=filter_date)
        return PlainTextResponse(csv_str, media_type="text/csv")

    @app.get("/journal/rejections")
    async def journal_rejections(date: Optional[str] = Query(None)) -> PlainTextResponse:
        from trading_base.journal.export import export_rejections_csv
        jp = _state["journal_path"]
        if jp is None:
            return PlainTextResponse("db not initialized", status_code=503)
        filter_date = _parse_date(date)
        csv_str = export_rejections_csv(jp, date_from=filter_date, date_to=filter_date)
        return PlainTextResponse(csv_str, media_type="text/csv")

    @app.get("/journal/today")
    async def journal_today():
        from trading_base.journal.export import export_rejections_csv, export_trades_csv
        jp = _state["journal_path"]
        if jp is None:
            return JSONResponse({"error": "db not initialized"}, status_code=503)
        today = date.today()
        trades_csv = export_trades_csv(jp, date_from=today, date_to=today)
        rejections_csv = export_rejections_csv(jp, date_from=today, date_to=today)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"trades_{today.isoformat()}.csv", trades_csv)
            zf.writestr(f"rejections_{today.isoformat()}.csv", rejections_csv)
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=journal_{today.isoformat()}.zip"},
        )

    # ── State mutation helpers (called by the strategy layer) ─────────────────

    @app.on_event("startup")
    async def _on_startup():
        logger.info("Webhook receiver started")

    def update_state(**kwargs) -> None:
        _state.update(kwargs)

    app.update_state = update_state  # type: ignore[attr-defined]

    return app


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        return None
