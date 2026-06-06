from __future__ import annotations

from decimal import Decimal

import pytest

from trading_base.broker.mock import MockBrokerAdapter
from trading_base.broker.protocol import BrokerAdapter
from trading_base.config import InstrumentCfg
from trading_base.constants import ExecutionStatus, ReconciliationState, TradingMode
from trading_base.models.submission_result import SubmissionResult


@pytest.fixture
def mock() -> MockBrokerAdapter:
    return MockBrokerAdapter()


@pytest.fixture
def mes_cfg() -> InstrumentCfg:
    return InstrumentCfg(
        symbol="MES", exchange="CME", currency="USD", instrument_type="FUTURES",
        point_value=Decimal("5"), tick_size=Decimal("0.25"), lot_size=1,
    )


def test_mock_satisfies_broker_protocol(mock):
    assert isinstance(mock, BrokerAdapter)


@pytest.mark.asyncio
async def test_mock_connect_sets_connected(mock):
    assert not mock.is_connected()
    await mock.connect()
    assert mock.is_connected()


@pytest.mark.asyncio
async def test_mock_disconnect_clears_connected(mock):
    await mock.connect()
    await mock.disconnect()
    assert not mock.is_connected()


@pytest.mark.asyncio
async def test_mock_get_account_equity_default(mock):
    equity = await mock.get_account_equity()
    assert isinstance(equity, Decimal)
    assert equity == Decimal("50000")


@pytest.mark.asyncio
async def test_mock_get_account_equity_custom():
    m = MockBrokerAdapter({"get_account_equity": Decimal("12345")})
    equity = await m.get_account_equity()
    assert equity == Decimal("12345")


@pytest.mark.asyncio
async def test_mock_get_account_equity_raises():
    m = MockBrokerAdapter({"get_account_equity": ValueError("unavailable")})
    with pytest.raises(ValueError):
        await m.get_account_equity()


@pytest.mark.asyncio
async def test_mock_get_open_positions_default(mock):
    positions = await mock.get_open_positions("MES")
    assert positions == []


@pytest.mark.asyncio
async def test_mock_get_open_orders_default(mock):
    orders = await mock.get_open_orders("MES")
    assert orders == []


@pytest.mark.asyncio
async def test_mock_submit_bracket_default(mock, mes_cfg):
    result = await mock.submit_bracket(
        Decimal("4500"), Decimal("4490"), Decimal("4520"), 1, mes_cfg
    )
    assert result.status == ExecutionStatus.SUBMITTED
    assert isinstance(result, SubmissionResult)


@pytest.mark.asyncio
async def test_mock_cancel_order_default(mock):
    assert await mock.cancel_order(1001)


@pytest.mark.asyncio
async def test_mock_close_position_market_default(mock, mes_cfg):
    result = await mock.close_position_market("MES", 1, mes_cfg)
    assert result.status == ExecutionStatus.SUBMITTED


@pytest.mark.asyncio
async def test_mock_reconcile_default(mock):
    result = await mock.reconcile_on_startup("MES")
    assert result.state == ReconciliationState.NO_POSITION


def test_mock_records_calls(mock):
    import asyncio
    asyncio.run(mock.connect())
    asyncio.run(mock.get_account_equity())
    assert "connect" in mock.calls
    assert "get_account_equity" in mock.calls


@pytest.mark.asyncio
async def test_mock_no_broker_calls_in_dev_mode(mes_cfg):
    """MockBrokerAdapter is always safe — it never calls a real broker."""
    mock = MockBrokerAdapter()
    await mock.connect()
    await mock.get_open_positions("MES")
    await mock.submit_bracket(Decimal("100"), Decimal("90"), Decimal("120"), 1, mes_cfg)
    assert "connect" in mock.calls
    assert "get_open_positions" in mock.calls
    assert "submit_bracket" in mock.calls
