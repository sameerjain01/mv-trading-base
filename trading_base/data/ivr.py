from __future__ import annotations

import sqlite3
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Optional

MIN_VALID_IV: Decimal = Decimal("0.10")
MAX_VALID_IV: Decimal = Decimal("2.00")

IV_PROXY_COEFFICIENTS: dict[str, Decimal] = {
    "SPY": Decimal("0.90"),
    "QQQ": Decimal("1.10"),
    "IWM": Decimal("1.15"),
    "DEFAULT": Decimal("1.00"),
}


class DataValidationError(ValueError):
    """Raised when an IV value is outside the acceptable range."""


def calculate_ivr(
    iv_series: list[Decimal],
    current_iv: Decimal,
    lookback: int = 252,
) -> Optional[Decimal]:
    """Return IVR 0–100. None if fewer than lookback values in series."""
    if len(iv_series) < lookback:
        return None
    window = iv_series[-lookback:]
    low = min(window)
    high = max(window)
    if high == low:
        return Decimal("50")
    ivr = ((current_iv - low) / (high - low) * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_EVEN
    )
    return max(Decimal("0"), min(Decimal("100"), ivr))


def iv_from_vix(vix: Decimal, symbol: str) -> Decimal:
    coeff = IV_PROXY_COEFFICIENTS.get(symbol.upper(), IV_PROXY_COEFFICIENTS["DEFAULT"])
    return (vix * coeff).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)


class IVRHistory:
    """Rolling IV history with SQLite persistence."""

    _CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS iv_history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            date      TEXT    NOT NULL UNIQUE,
            iv        TEXT    NOT NULL
        );
    """

    def __init__(self, lookback: int = 252) -> None:
        self._lookback = lookback
        self._history: list[tuple[date, Decimal]] = []

    def add(self, d: date, iv: Decimal) -> None:
        if not (MIN_VALID_IV <= iv <= MAX_VALID_IV):
            raise DataValidationError(
                f"IV value {iv} on {d} is outside valid range "
                f"[{MIN_VALID_IV}, {MAX_VALID_IV}]"
            )
        self._history.append((d, iv))
        if len(self._history) > self._lookback * 2:
            self._history = self._history[-self._lookback * 2:]

    def current_ivr(self) -> Optional[Decimal]:
        if not self._history:
            return None
        series = [iv for _, iv in self._history]
        current = series[-1]
        return calculate_ivr(series, current, self._lookback)

    def load_from_db(self, db_path: Path) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute(self._CREATE_TABLE)
            rows = conn.execute(
                "SELECT date, iv FROM iv_history ORDER BY date ASC"
            ).fetchall()
        self._history = [
            (date.fromisoformat(r[0]), Decimal(r[1])) for r in rows
        ]

    def save_to_db(self, db_path: Path) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute(self._CREATE_TABLE)
            conn.executemany(
                "INSERT OR REPLACE INTO iv_history (date, iv) VALUES (?, ?)",
                [(d.isoformat(), str(iv)) for d, iv in self._history],
            )
