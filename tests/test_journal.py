from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from trading_base.journal.export import (
    RiskAdjustedMetrics,
    compute_risk_adjusted_pnl,
    export_rejections_csv,
    export_trades_csv,
)
from trading_base.journal.writer import (
    init_db,
    update_trade_exit,
    write_rejection,
    write_system_event,
    write_trade,
)


def test_init_db_creates_tables(tmp_path):
    db = tmp_path / "j.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "trades" in tables
    assert "rejections" in tables
    assert "system_events" in tables


def test_init_db_idempotent(tmp_path):
    db = tmp_path / "j.db"
    init_db(db)
    init_db(db)  # second call must not raise


def test_write_trade_inserts(tmp_db, sample_trade):
    write_trade(tmp_db, sample_trade)
    with sqlite3.connect(tmp_db) as conn:
        row = conn.execute("SELECT trade_id FROM trades WHERE trade_id = ?", ("trade-001",)).fetchone()
    assert row is not None


def test_write_trade_duplicate_skipped(tmp_db, sample_trade):
    write_trade(tmp_db, sample_trade)
    write_trade(tmp_db, sample_trade)  # should not raise
    with sqlite3.connect(tmp_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM trades WHERE trade_id = ?", ("trade-001",)).fetchone()[0]
    assert count == 1


def test_update_trade_exit(tmp_db, sample_trade):
    write_trade(tmp_db, sample_trade)
    from decimal import Decimal
    from datetime import datetime, timezone
    from types import MappingProxyType
    from trading_base.constants import ExitReason, Regime, SignalAction
    updated = sample_trade.__class__(
        **{**sample_trade.__dict__, "exit_price": Decimal("4525.00"), "net_pnl": Decimal("120.00")}
    )
    update_trade_exit(tmp_db, "trade-001", updated)
    with sqlite3.connect(tmp_db) as conn:
        row = conn.execute("SELECT exit_price, net_pnl FROM trades WHERE trade_id = ?", ("trade-001",)).fetchone()
    assert Decimal(row[0]) == Decimal("4525.00")


def test_write_rejection_inserts(tmp_db, sample_rejection):
    write_rejection(tmp_db, sample_rejection)
    with sqlite3.connect(tmp_db) as conn:
        row = conn.execute("SELECT rejection_id FROM rejections WHERE rejection_id = ?", ("rej-001",)).fetchone()
    assert row is not None


def test_write_system_event(tmp_db):
    write_system_event(tmp_db, "STARTUP", "system started", {"mode": "paper"})
    with sqlite3.connect(tmp_db) as conn:
        row = conn.execute("SELECT event_type FROM system_events WHERE event_type = 'STARTUP'").fetchone()
    assert row is not None


def test_export_trades_csv_headers(tmp_db, sample_trade):
    write_trade(tmp_db, sample_trade)
    csv_str = export_trades_csv(tmp_db)
    lines = csv_str.strip().splitlines()
    assert lines[0].startswith("trade_id")
    assert len(lines) == 2  # header + 1 row


def test_export_rejections_csv_headers(tmp_db, sample_rejection):
    write_rejection(tmp_db, sample_rejection)
    csv_str = export_rejections_csv(tmp_db)
    lines = csv_str.strip().splitlines()
    assert lines[0].startswith("rejection_id")
    assert len(lines) == 2


def test_compute_risk_adjusted_pnl_insufficient():
    m = compute_risk_adjusted_pnl([Decimal("100"), Decimal("-50")], window=10)
    assert m.insufficient_data
    assert m.avg_net_pnl == Decimal("0")


def test_compute_risk_adjusted_pnl_sufficient():
    pnls = [Decimal("100")] * 10 + [Decimal("-50")] * 10 + [Decimal("75")] * 10
    m = compute_risk_adjusted_pnl(pnls, window=30)
    assert not m.insufficient_data
    assert isinstance(m.avg_net_pnl, Decimal)
    assert isinstance(m.stdev_net_pnl, Decimal)
    assert isinstance(m.sharpe_equivalent, Decimal)
