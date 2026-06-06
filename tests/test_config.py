from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from trading_base.config import ConfigError, load_config
from trading_base.constants import TradingMode


VALID_YAML = """\
instrument:
  symbol: MES
  exchange: CME
  currency: USD
  instrument_type: FUTURES
  point_value: "5"
  tick_size: "0.25"
  lot_size: 1

ibkr:
  host: "127.0.0.1"
  paper_port: 4002
  live_port: 4001
  client_id: 1
  connection_timeout_seconds: 10

risk:
  max_contracts: 2
  risk_pct: "0.01"
  daily_loss_cap_pct: "0.02"
  min_stop_atr_multiple: "0.5"
  max_stop_atr_multiple: "3.0"
  rr_ratio: "2.0"
  consecutive_loss_threshold: 3
  consecutive_loss_cooldown_hours: 4

execution:
  max_spread_ticks: 4
  max_price_deviation_ticks: 8
  webhook_port: 8000
  entry_timeout_seconds: 30
  bracket_confirm_seconds: 10
  slippage_ticks: 1

session:
  signal_staleness_seconds: 60
  timezone: "America/New_York"
  session_open_hour: 18
  session_open_minute: 0
  session_close_hour: 17
  session_close_minute: 0
  entry_blackout_open_minutes: 15
  entry_blackout_close_minutes: 30
  session_end_liquidation_hour: 16
  session_end_liquidation_minute: 55
  presession_check_hour: 17
  presession_check_minute: 50
  news_blackout_minutes: 30

regime:
  regime_refresh_minutes: 15
  poll_interval_sec: 60

calendar:
  api_url: "https://finnhub.io/api/v1/calendar/economic"
  cache_hours: 1

doctrine:
  edge_warning_win_rate: "0.40"
  edge_reduction_win_rate: "0.30"
  edge_suspension_win_rate: "0.20"
  edge_reduction_consecutive_weeks: 2
  rolling_window_trades: 10
  risk_adjusted_window_trades: 30
  hypothetical_lookback_minutes: 60
  hypothetical_price_window_minutes: 120
"""


@pytest.fixture
def config_path(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(VALID_YAML)
    return p


def test_valid_yaml_loads(config_path):
    cfg = load_config(config_path)
    assert cfg.instrument.symbol == "MES"
    from decimal import Decimal
    assert cfg.instrument.point_value == Decimal("5")
    assert cfg.instrument.tick_size == Decimal("0.25")


def test_port_for_paper(config_path):
    cfg = load_config(config_path)
    assert cfg.ibkr.port_for(TradingMode.PAPER) == 4002


def test_port_for_live(config_path):
    cfg = load_config(config_path)
    assert cfg.ibkr.port_for(TradingMode.LIVE) == 4001


def test_port_for_dev_raises(config_path):
    cfg = load_config(config_path)
    with pytest.raises(ValueError):
        cfg.ibkr.port_for(TradingMode.DEV)


def test_missing_section_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("ibkr:\n  host: x\n")
    with pytest.raises(ConfigError):
        load_config(p)


def test_invalid_risk_pct_raises(tmp_path):
    bad = VALID_YAML.replace('risk_pct: "0.01"', 'risk_pct: "0.99"')
    p = tmp_path / "bad.yaml"
    p.write_text(bad)
    with pytest.raises(ConfigError):
        load_config(p)
