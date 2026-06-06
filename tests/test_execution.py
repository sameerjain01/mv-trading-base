from __future__ import annotations

from decimal import Decimal

import pytest

from trading_base.config import InstrumentCfg
from trading_base.execution.bracket import BracketOrder, InvalidOrderError, build_bracket_order


@pytest.fixture
def mes_cfg() -> InstrumentCfg:
    return InstrumentCfg(
        symbol="MES",
        exchange="CME",
        currency="USD",
        instrument_type="FUTURES",
        point_value=Decimal("5"),
        tick_size=Decimal("0.25"),
        lot_size=1,
    )


def _build(entry, stop, target, qty, cfg):
    """Helper: build bracket without needing ib_async installed."""
    try:
        return build_bracket_order(Decimal(str(entry)), Decimal(str(stop)), Decimal(str(target)), qty, cfg)
    except ImportError:
        pytest.skip("ib_async not installed")


def test_build_bracket_basic(mes_cfg):
    bracket = _build("4500.00", "4490.00", "4520.00", 1, mes_cfg)
    assert isinstance(bracket, BracketOrder)
    assert bracket.oca_group
    assert len(bracket.oca_group) == 36  # UUID4


def test_build_bracket_invalid_quantity(mes_cfg):
    with pytest.raises(InvalidOrderError):
        _build("4500", "4490", "4520", 0, mes_cfg)


def test_build_bracket_stop_above_entry_raises(mes_cfg):
    with pytest.raises(InvalidOrderError):
        _build("4500", "4510", "4520", 1, mes_cfg)


def test_build_bracket_target_below_entry_raises(mes_cfg):
    with pytest.raises(InvalidOrderError):
        _build("4500", "4490", "4495", 1, mes_cfg)


def test_build_bracket_quantizes_to_tick(mes_cfg):
    # 4500.13 → nearest 0.25 tick
    try:
        bracket = build_bracket_order(
            Decimal("4500.13"), Decimal("4490.00"), Decimal("4520.00"), 1, mes_cfg
        )
        # entry should be quantized; float stored in ib_async object
        entry_price = bracket.entry.lmtPrice
        # 4500.13 / 0.25 = 18000.52 → round → 18001 × 0.25 = 4500.25
        assert abs(entry_price - 4500.25) < 0.01
    except ImportError:
        pytest.skip("ib_async not installed")


def test_build_bracket_tick_size_respected_for_different_instrument():
    cfg_01 = InstrumentCfg(
        symbol="QQQ", exchange="SMART", currency="USD", instrument_type="STOCK",
        point_value=Decimal("1"), tick_size=Decimal("0.01"), lot_size=1,
    )
    try:
        bracket = build_bracket_order(
            Decimal("400.123"), Decimal("399.00"), Decimal("402.00"), 10, cfg_01
        )
        # 400.123 → nearest 0.01 → 400.12
        assert abs(bracket.entry.lmtPrice - 400.12) < 0.001
    except ImportError:
        pytest.skip("ib_async not installed")
