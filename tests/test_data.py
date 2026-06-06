from __future__ import annotations

from decimal import Decimal

import pytest

from trading_base.data.ivr import IVRHistory, calculate_ivr, iv_from_vix


def test_calculate_ivr_at_max():
    series = [Decimal(str(i)) for i in range(1, 253)]
    result = calculate_ivr(series, Decimal("252"), lookback=252)
    assert result == Decimal("100")


def test_calculate_ivr_at_min():
    series = [Decimal(str(i)) for i in range(1, 253)]
    result = calculate_ivr(series, Decimal("1"), lookback=252)
    assert result == Decimal("0")


def test_calculate_ivr_midpoint():
    series = [Decimal(str(i)) for i in range(1, 253)]
    result = calculate_ivr(series, Decimal("127"), lookback=252)
    assert Decimal("40") <= result <= Decimal("60")


def test_calculate_ivr_insufficient_history_returns_none():
    series = [Decimal("20")] * 10
    result = calculate_ivr(series, Decimal("20"), lookback=252)
    assert result is None


def test_calculate_ivr_result_is_decimal():
    series = [Decimal(str(i)) for i in range(1, 253)]
    result = calculate_ivr(series, Decimal("100"), lookback=252)
    assert isinstance(result, Decimal)


def test_iv_from_vix_spy():
    vix = Decimal("20")
    iv = iv_from_vix(vix, "SPY")
    assert isinstance(iv, Decimal)
    # SPY coefficient is 0.90
    assert iv == (vix * Decimal("0.90")).quantize(Decimal("0.0001"))


def test_iv_from_vix_qqq():
    vix = Decimal("20")
    iv = iv_from_vix(vix, "QQQ")
    # QQQ coefficient is 1.10
    assert iv == (vix * Decimal("1.10")).quantize(Decimal("0.0001"))


def test_iv_from_vix_unknown_uses_default():
    vix = Decimal("20")
    iv = iv_from_vix(vix, "UNKNOWN")
    # DEFAULT coefficient is 1.00
    assert iv == vix.quantize(Decimal("0.0001"))


def test_ivr_history_add_and_compute(tmp_path):
    h = IVRHistory(lookback=252)
    for i in range(1, 253):
        from datetime import date
        d = date(2025, 1, 1)
        # simulate different dates by using index as date offset
        h.add(d, Decimal(str(i)))
    result = h.current_ivr()
    assert result is not None
    assert isinstance(result, Decimal)


def test_ivr_history_insufficient_returns_none():
    h = IVRHistory(lookback=252)
    from datetime import date
    h.add(date(2025, 1, 1), Decimal("20"))
    assert h.current_ivr() is None


def test_ivr_history_persist_and_load(tmp_path):
    db = tmp_path / "ivr.db"
    h = IVRHistory(lookback=5)
    from datetime import date
    for i in range(5):
        h.add(date(2025, 1, i + 1), Decimal(str(i + 1)))
    h.save_to_db(db)

    h2 = IVRHistory(lookback=5)
    h2.load_from_db(db)
    result = h2.current_ivr()
    assert result is not None
