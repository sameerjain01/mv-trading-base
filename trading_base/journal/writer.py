from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from trading_base.models.rejection import Rejection
from trading_base.models.trade import Trade

logger = logging.getLogger(__name__)


def init_db(db_path: Path) -> None:
    """Create all journal tables if they do not exist. Safe to call multiple times."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id                TEXT PRIMARY KEY,
                timestamp_signal        TEXT NOT NULL,
                timestamp_entry         TEXT NOT NULL,
                timestamp_exit          TEXT NOT NULL,
                direction               TEXT NOT NULL,
                entry_price             TEXT NOT NULL,
                stop_price              TEXT NOT NULL,
                target_price            TEXT NOT NULL,
                stop_distance_points    TEXT NOT NULL,
                target_distance_points  TEXT NOT NULL,
                rr_ratio                TEXT NOT NULL,
                quantity                INTEGER NOT NULL,
                support_level           TEXT NOT NULL,
                resistance_level        TEXT NOT NULL,
                regime_at_entry         TEXT NOT NULL,
                vix_at_entry            TEXT NOT NULL,
                market_context          TEXT NOT NULL,
                filters_fired           TEXT NOT NULL,
                exit_reason             TEXT NOT NULL,
                exit_price              TEXT NOT NULL,
                gross_pnl               TEXT NOT NULL,
                commission              TEXT NOT NULL,
                slippage_applied        TEXT NOT NULL,
                net_pnl                 TEXT NOT NULL,
                assumption              TEXT NOT NULL,
                outcome_note            TEXT NOT NULL,
                expiry                  TEXT,
                strike                  TEXT,
                put_call                TEXT,
                delta                   TEXT
            );

            CREATE TABLE IF NOT EXISTS rejections (
                rejection_id            TEXT PRIMARY KEY,
                timestamp               TEXT NOT NULL,
                signal_id               TEXT NOT NULL,
                symbol                  TEXT NOT NULL,
                action                  TEXT NOT NULL,
                signal_price            TEXT NOT NULL,
                stop_price              TEXT NOT NULL,
                rejection_code          TEXT NOT NULL,
                rejection_reason        TEXT NOT NULL,
                regime_at_rejection     TEXT NOT NULL,
                hypothetical_outcome    TEXT,
                hypothetical_pnl        TEXT
            );

            CREATE TABLE IF NOT EXISTS system_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                event_type  TEXT NOT NULL,
                message     TEXT NOT NULL,
                extra_json  TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_rejections_outcome_ts
                ON rejections(hypothetical_outcome, timestamp);
        """)


def write_trade(db_path: Path, trade: Trade) -> None:
    row = trade.to_csv_row()
    with sqlite3.connect(db_path) as conn:
        existing = conn.execute(
            "SELECT 1 FROM trades WHERE trade_id = ?", (trade.trade_id,)
        ).fetchone()
        if existing:
            logger.warning(
                "write_trade: duplicate trade_id, skipping",
                extra={"trade_id": trade.trade_id},
            )
            return
        conn.execute(
            "INSERT INTO trades VALUES " + ("(?" + ",?" * 29 + ")"),
            row,
        )
    logger.info("Trade written", extra={"trade_id": trade.trade_id})


def update_trade_exit(db_path: Path, trade_id: str, updated_trade: Trade) -> None:
    d = updated_trade.to_dict()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """UPDATE trades SET
               timestamp_exit=?, exit_reason=?, exit_price=?,
               gross_pnl=?, commission=?, slippage_applied=?, net_pnl=?, outcome_note=?
               WHERE trade_id=?""",
            (
                d["timestamp_exit"], d["exit_reason"], d["exit_price"],
                d["gross_pnl"], d["commission"], d["slippage_applied"],
                d["net_pnl"], d["outcome_note"],
                trade_id,
            ),
        )
    logger.info("Trade exit updated", extra={"trade_id": trade_id})


def write_rejection(db_path: Path, rejection: Rejection) -> None:
    row = rejection.to_csv_row()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO rejections VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            row,
        )
    logger.info(
        "Rejection written",
        extra={
            "rejection_id": rejection.rejection_id,
            "code": rejection.rejection_code.value,
        },
    )


def write_system_event(
    db_path: Path,
    event_type: str,
    message: str,
    extra: dict | None = None,
) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    extra_json = json.dumps(extra) if extra else None
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO system_events (timestamp, event_type, message, extra_json) VALUES (?,?,?,?)",
            (ts, event_type, message, extra_json),
        )
    logger.info("System event written", extra={"event_type": event_type, "event_msg": message})
