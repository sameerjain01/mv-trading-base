from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pytest

from trading_base.broker.mock import MockBrokerAdapter
from trading_base.config import (
    AppConfig, CalendarCfg, DoctrineCfg, ExecutionCfg, IBKRCfg,
    InstrumentCfg, RegimeCfg, RiskCfg, SessionCfg,
)
from trading_base.constants import (
    ExitReason, Regime, RejectionCode, SignalAction, TradingMode,
)
from trading_base.models.rejection import Rejection
from trading_base.models.trade import Trade


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def instrument_cfg() -> InstrumentCfg:
    return InstrumentCfg(
        symbol="MES",
        exchange="CME",
        currency="USD",
        instrument_type="FUTURES",
        point_value=Decimal("5"),
        tick_size=Decimal("0.25"),
        lot_size=1,
    )


@pytest.fixture
def risk_cfg() -> RiskCfg:
    return RiskCfg(
        max_contracts=2,
        risk_pct=Decimal("0.01"),
        daily_loss_cap_pct=Decimal("0.02"),
        min_stop_atr_multiple=Decimal("0.5"),
        max_stop_atr_multiple=Decimal("3.0"),
        rr_ratio=Decimal("2.0"),
        consecutive_loss_threshold=3,
        consecutive_loss_cooldown_hours=4,
    )


@pytest.fixture
def app_config(instrument_cfg, risk_cfg) -> AppConfig:
    return AppConfig(
        instrument=instrument_cfg,
        ibkr=IBKRCfg(
            host="127.0.0.1",
            paper_port=4002,
            live_port=4001,
            client_id=1,
            connection_timeout_seconds=10,
        ),
        risk=risk_cfg,
        execution=ExecutionCfg(
            max_spread_ticks=4,
            max_price_deviation_ticks=8,
            webhook_port=8000,
            entry_timeout_seconds=30,
            bracket_confirm_seconds=10,
            slippage_ticks=1,
        ),
        session=SessionCfg(
            signal_staleness_seconds=60,
            timezone="America/New_York",
            session_open_hour=18,
            session_open_minute=0,
            session_close_hour=17,
            session_close_minute=0,
            entry_blackout_open_minutes=15,
            entry_blackout_close_minutes=30,
            session_end_liquidation_hour=16,
            session_end_liquidation_minute=55,
            presession_check_hour=17,
            presession_check_minute=50,
            news_blackout_minutes=30,
        ),
        regime=RegimeCfg(regime_refresh_minutes=15, poll_interval_sec=60),
        calendar=CalendarCfg(api_url="https://finnhub.io/api/v1/calendar/economic", cache_hours=1),
        doctrine=DoctrineCfg(
            edge_warning_win_rate=Decimal("0.40"),
            edge_reduction_win_rate=Decimal("0.30"),
            edge_suspension_win_rate=Decimal("0.20"),
            edge_reduction_consecutive_weeks=2,
            rolling_window_trades=10,
            risk_adjusted_window_trades=30,
            hypothetical_lookback_minutes=60,
            hypothetical_price_window_minutes=120,
        ),
    )


@pytest.fixture
def mock_broker() -> MockBrokerAdapter:
    return MockBrokerAdapter()


@pytest.fixture
def tmp_db(tmp_path) -> Path:
    db = tmp_path / "journal.db"
    from trading_base.journal.writer import init_db
    init_db(db)
    return db


@pytest.fixture
def sample_trade() -> Trade:
    now = datetime.now(timezone.utc)
    return Trade(
        trade_id="trade-001",
        timestamp_signal=now,
        timestamp_entry=now,
        timestamp_exit=now,
        direction=SignalAction.BUY,
        entry_price=Decimal("4500.00"),
        stop_price=Decimal("4490.00"),
        target_price=Decimal("4520.00"),
        stop_distance_points=Decimal("10.00"),
        target_distance_points=Decimal("20.00"),
        rr_ratio=Decimal("2.00"),
        quantity=1,
        support_level=Decimal("4488.00"),
        resistance_level=Decimal("4522.00"),
        regime_at_entry=Regime.TRENDING,
        vix_at_entry=Decimal("18.50"),
        market_context="ABOVE_20MA",
        filters_fired=MappingProxyType({}),
        exit_reason=ExitReason.TAKE_PROFIT,
        exit_price=Decimal("4520.00"),
        gross_pnl=Decimal("100.00"),
        commission=Decimal("2.10"),
        slippage_applied=Decimal("1.25"),
        net_pnl=Decimal("96.65"),
        assumption="Strong trend continuation",
        outcome_note="Target hit cleanly",
    )


@pytest.fixture
def sample_rejection() -> Rejection:
    return Rejection(
        rejection_id="rej-001",
        timestamp=datetime.now(timezone.utc),
        signal_id="sig-001",
        symbol="MES",
        action=SignalAction.BUY,
        signal_price=Decimal("4500.00"),
        stop_price=Decimal("4490.00"),
        rejection_code=RejectionCode.REGIME_CHOPPY,
        rejection_reason="regime is CHOPPY",
        regime_at_rejection=Regime.CHOPPY,
    )
