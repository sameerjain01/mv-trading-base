from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path
from typing import Optional

from trading_base.constants import Precision
from trading_base.models.rejection import REJECTION_FIELDS
from trading_base.models.trade import JOURNAL_FIELDS


@dataclass(frozen=True)
class RiskAdjustedMetrics:
    avg_net_pnl: Decimal
    stdev_net_pnl: Decimal
    sharpe_equivalent: Decimal
    is_positive: bool
    insufficient_data: bool


def compute_risk_adjusted_pnl(
    pnl_list: list[Decimal],
    window: int = 30,
) -> RiskAdjustedMetrics:
    """Compute avg, stdev, and sharpe-equivalent over the last `window` trade PnLs."""
    subset = pnl_list[-window:]
    zero = Decimal("0")
    if len(subset) < window:
        return RiskAdjustedMetrics(
            avg_net_pnl=zero,
            stdev_net_pnl=zero,
            sharpe_equivalent=zero,
            is_positive=False,
            insufficient_data=True,
        )

    n = len(subset)
    avg = (sum(subset) / n).quantize(Precision.AMOUNT, ROUND_HALF_EVEN)
    variance = sum((p - avg) ** 2 for p in subset) / n
    with localcontext() as ctx:
        ctx.prec = 28
        stdev = variance.sqrt().quantize(Precision.AMOUNT, rounding=ROUND_HALF_EVEN)

    sharpe = (avg / stdev).quantize(Precision.RATE, ROUND_HALF_EVEN) if stdev != zero else zero

    return RiskAdjustedMetrics(
        avg_net_pnl=avg,
        stdev_net_pnl=stdev,
        sharpe_equivalent=sharpe,
        is_positive=sharpe > zero,
        insufficient_data=False,
    )


def export_trades_csv(
    db_path: Path,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> str:
    conditions: list[str] = []
    params: list[str] = []
    if date_from:
        conditions.append("date(timestamp_entry) >= ?")
        params.append(date_from.isoformat())
    if date_to:
        conditions.append("date(timestamp_entry) <= ?")
        params.append(date_to.isoformat())

    query = "SELECT " + ", ".join(JOURNAL_FIELDS) + " FROM trades"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY timestamp_entry"

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(JOURNAL_FIELDS)
    writer.writerows(rows)
    return buf.getvalue()


def export_rejections_csv(
    db_path: Path,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> str:
    conditions: list[str] = []
    params: list[str] = []
    if date_from:
        conditions.append("date(timestamp) >= ?")
        params.append(date_from.isoformat())
    if date_to:
        conditions.append("date(timestamp) <= ?")
        params.append(date_to.isoformat())

    query = "SELECT " + ", ".join(REJECTION_FIELDS) + " FROM rejections"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY timestamp"

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(REJECTION_FIELDS)
    writer.writerows(rows)
    return buf.getvalue()


def weekly_review(db_path: Path) -> dict:
    """Return summary counts from the current week's journal records."""
    with sqlite3.connect(db_path) as conn:
        trade_count = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE date(timestamp_entry) >= date('now', 'weekday 1', '-7 days')"
        ).fetchone()[0]
        rejection_count = conn.execute(
            "SELECT COUNT(*) FROM rejections WHERE date(timestamp) >= date('now', 'weekday 1', '-7 days')"
        ).fetchone()[0]
        net_pnl_rows = conn.execute(
            "SELECT net_pnl FROM trades WHERE date(timestamp_entry) >= date('now', 'weekday 1', '-7 days')"
        ).fetchall()

    pnls = [Decimal(r[0]) for r in net_pnl_rows if r[0] is not None]
    total_pnl = sum(pnls, Decimal("0")).quantize(Precision.AMOUNT, ROUND_HALF_EVEN)
    win_rate = (
        Decimal(sum(1 for p in pnls if p > 0)) / Decimal(len(pnls))
        if pnls
        else None
    )

    return {
        "trade_count": trade_count,
        "rejection_count": rejection_count,
        "total_net_pnl": str(total_pnl),
        "win_rate": str(win_rate.quantize(Precision.RATE, ROUND_HALF_EVEN)) if win_rate is not None else None,
    }
