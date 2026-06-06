from __future__ import annotations

import pytest

from trading_base.broker.ibkr import IBKRAdapter
from trading_base.config import IBKRCfg, InstrumentCfg
from trading_base.constants import TradingMode
from decimal import Decimal


@pytest.fixture
def ibkr_cfg() -> IBKRCfg:
    return IBKRCfg(
        host="127.0.0.1",
        paper_port=4002,
        live_port=4001,
        client_id=1,
        connection_timeout_seconds=10,
    )


@pytest.fixture
def mes_cfg() -> InstrumentCfg:
    return InstrumentCfg(
        symbol="MES", exchange="CME", currency="USD", instrument_type="FUTURES",
        point_value=Decimal("5"), tick_size=Decimal("0.25"), lot_size=1,
    )


@pytest.mark.asyncio
async def test_dev_mode_connect_does_not_call_ibkr(ibkr_cfg, mes_cfg):
    adapter = IBKRAdapter(ibkr_cfg, TradingMode.DEV, mes_cfg)
    await adapter.connect()
    assert not adapter.is_connected()  # DEV: no real connection


@pytest.mark.asyncio
async def test_dev_mode_get_account_equity_raises(ibkr_cfg, mes_cfg):
    from trading_base.broker.ibkr import IBKRDataError
    adapter = IBKRAdapter(ibkr_cfg, TradingMode.DEV, mes_cfg)
    with pytest.raises(IBKRDataError):
        await adapter.get_account_equity()


@pytest.mark.asyncio
async def test_dev_mode_submit_bracket_returns_submitted(ibkr_cfg, mes_cfg):
    from trading_base.constants import ExecutionStatus
    adapter = IBKRAdapter(ibkr_cfg, TradingMode.DEV, mes_cfg)
    result = await adapter.submit_bracket(
        Decimal("4500"), Decimal("4490"), Decimal("4520"), 1, mes_cfg
    )
    assert result.status == ExecutionStatus.SUBMITTED


@pytest.mark.asyncio
async def test_dev_mode_reconcile_returns_no_position(ibkr_cfg, mes_cfg):
    from trading_base.constants import ReconciliationState
    adapter = IBKRAdapter(ibkr_cfg, TradingMode.DEV, mes_cfg)
    result = await adapter.reconcile_on_startup("MES")
    assert result.state == ReconciliationState.NO_POSITION


def test_build_contract_futures(mes_cfg):
    try:
        contract = IBKRAdapter._build_contract(mes_cfg)
        assert contract.symbol == "MES"
    except ImportError:
        pytest.skip("ib_async not installed")


def test_build_contract_unknown_type_raises():
    cfg = InstrumentCfg(
        symbol="X", exchange="Y", currency="USD", instrument_type="CRYPTO",
        point_value=Decimal("1"), tick_size=Decimal("0.01"), lot_size=1,
    )
    with pytest.raises(ValueError, match="Unsupported instrument_type"):
        IBKRAdapter._build_contract(cfg)


@pytest.mark.slow
@pytest.mark.asyncio
async def test_paper_account_connect(ibkr_cfg, mes_cfg):
    """Requires live IBKR paper account on 127.0.0.1:4002."""
    adapter = IBKRAdapter(ibkr_cfg, TradingMode.PAPER, mes_cfg)
    await adapter.connect()
    assert adapter.is_connected()
    equity = await adapter.get_account_equity()
    assert isinstance(equity, Decimal)
    assert equity > Decimal("0")
    await adapter.disconnect()
