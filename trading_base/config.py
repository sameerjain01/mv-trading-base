from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

from trading_base.constants import TradingMode


class ConfigError(Exception):
    pass


def _require(d: dict, key: str, section: str):
    if key not in d:
        raise ConfigError(f"Missing required config key: {section}.{key}")
    return d[key]


def _section(raw: dict, name: str) -> dict:
    if name not in raw:
        raise ConfigError(f"Missing required config section: {name}")
    return raw[name]


def _dec(d: dict, key: str, section: str) -> Decimal:
    return Decimal(str(_require(d, key, section)))


# ── Instrument ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class InstrumentCfg:
    symbol: str
    exchange: str
    currency: str
    instrument_type: str       # STOCK | FUTURES | OPTION
    point_value: Decimal       # dollars per full point
    tick_size: Decimal         # minimum price increment in points
    lot_size: int              # minimum order quantity (1 for futures/equities)


# ── IBKR ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class IBKRCfg:
    host: str
    paper_port: int
    live_port: int
    client_id: int
    connection_timeout_seconds: int

    def port_for(self, mode: TradingMode) -> int:
        if mode == TradingMode.DEV:
            raise ValueError("DEV mode must not connect to IBKR")
        if mode == TradingMode.LIVE:
            return self.live_port
        return self.paper_port


# ── Risk ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RiskCfg:
    max_contracts: int
    risk_pct: Decimal                     # flat default; strategy adjusts per regime
    daily_loss_cap_pct: Decimal
    min_stop_atr_multiple: Decimal
    max_stop_atr_multiple: Decimal
    rr_ratio: Decimal
    consecutive_loss_threshold: int
    consecutive_loss_cooldown_hours: int


# ── Execution ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ExecutionCfg:
    max_spread_ticks: int                 # max spread in ticks (× tick_size = dollars)
    max_price_deviation_ticks: int
    webhook_port: int
    entry_timeout_seconds: int
    bracket_confirm_seconds: int
    slippage_ticks: int


# ── Session ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SessionCfg:
    signal_staleness_seconds: int
    timezone: str
    session_open_hour: int
    session_open_minute: int
    session_close_hour: int
    session_close_minute: int
    entry_blackout_open_minutes: int
    entry_blackout_close_minutes: int
    session_end_liquidation_hour: int
    session_end_liquidation_minute: int
    presession_check_hour: int
    presession_check_minute: int
    news_blackout_minutes: int


# ── Regime ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RegimeCfg:
    regime_refresh_minutes: int
    poll_interval_sec: int


# ── Calendar ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CalendarCfg:
    api_url: str
    cache_hours: int


# ── Doctrine ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DoctrineCfg:
    edge_warning_win_rate: Decimal
    edge_reduction_win_rate: Decimal
    edge_suspension_win_rate: Decimal
    edge_reduction_consecutive_weeks: int
    rolling_window_trades: int
    risk_adjusted_window_trades: int
    hypothetical_lookback_minutes: int
    hypothetical_price_window_minutes: int


# ── Root config ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AppConfig:
    instrument: InstrumentCfg
    ibkr: IBKRCfg
    risk: RiskCfg
    execution: ExecutionCfg
    session: SessionCfg
    regime: RegimeCfg
    calendar: CalendarCfg
    doctrine: DoctrineCfg


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_instrument(raw: dict) -> InstrumentCfg:
    d = _section(raw, "instrument")
    cfg = InstrumentCfg(
        symbol=_require(d, "symbol", "instrument"),
        exchange=_require(d, "exchange", "instrument"),
        currency=_require(d, "currency", "instrument"),
        instrument_type=_require(d, "instrument_type", "instrument"),
        point_value=_dec(d, "point_value", "instrument"),
        tick_size=_dec(d, "tick_size", "instrument"),
        lot_size=_require(d, "lot_size", "instrument"),
    )
    if cfg.point_value <= 0:
        raise ConfigError(f"instrument.point_value must be positive, got {cfg.point_value}")
    if cfg.tick_size <= 0:
        raise ConfigError(f"instrument.tick_size must be positive, got {cfg.tick_size}")
    if cfg.lot_size < 1:
        raise ConfigError(f"instrument.lot_size must be >= 1, got {cfg.lot_size}")
    return cfg


def _load_ibkr(raw: dict) -> IBKRCfg:
    d = _section(raw, "ibkr")
    cfg = IBKRCfg(
        host=_require(d, "host", "ibkr"),
        paper_port=_require(d, "paper_port", "ibkr"),
        live_port=_require(d, "live_port", "ibkr"),
        client_id=_require(d, "client_id", "ibkr"),
        connection_timeout_seconds=_require(d, "connection_timeout_seconds", "ibkr"),
    )
    if cfg.connection_timeout_seconds <= 0:
        raise ConfigError(
            f"ibkr.connection_timeout_seconds must be positive, got {cfg.connection_timeout_seconds}"
        )
    return cfg


def _load_risk(raw: dict) -> RiskCfg:
    d = _section(raw, "risk")
    cfg = RiskCfg(
        max_contracts=_require(d, "max_contracts", "risk"),
        risk_pct=_dec(d, "risk_pct", "risk"),
        daily_loss_cap_pct=_dec(d, "daily_loss_cap_pct", "risk"),
        min_stop_atr_multiple=_dec(d, "min_stop_atr_multiple", "risk"),
        max_stop_atr_multiple=_dec(d, "max_stop_atr_multiple", "risk"),
        rr_ratio=_dec(d, "rr_ratio", "risk"),
        consecutive_loss_threshold=_require(d, "consecutive_loss_threshold", "risk"),
        consecutive_loss_cooldown_hours=_require(d, "consecutive_loss_cooldown_hours", "risk"),
    )
    if cfg.max_contracts < 1:
        raise ConfigError(f"risk.max_contracts must be >= 1, got {cfg.max_contracts}")
    if not (Decimal("0") < cfg.risk_pct < Decimal("0.05")):
        raise ConfigError(f"risk.risk_pct out of bounds (0, 0.05): {cfg.risk_pct}")
    if not (Decimal("0") < cfg.daily_loss_cap_pct < Decimal("0.1")):
        raise ConfigError(f"risk.daily_loss_cap_pct out of bounds (0, 0.1): {cfg.daily_loss_cap_pct}")
    if not (Decimal("0") < cfg.rr_ratio <= Decimal("10")):
        raise ConfigError(f"risk.rr_ratio out of bounds (0, 10]: {cfg.rr_ratio}")
    if not (Decimal("0") < cfg.min_stop_atr_multiple < cfg.max_stop_atr_multiple):
        raise ConfigError(
            f"risk.min_stop_atr_multiple must be < max_stop_atr_multiple: "
            f"{cfg.min_stop_atr_multiple} vs {cfg.max_stop_atr_multiple}"
        )
    return cfg


def _load_execution(raw: dict) -> ExecutionCfg:
    d = _section(raw, "execution")
    return ExecutionCfg(
        max_spread_ticks=_require(d, "max_spread_ticks", "execution"),
        max_price_deviation_ticks=_require(d, "max_price_deviation_ticks", "execution"),
        webhook_port=_require(d, "webhook_port", "execution"),
        entry_timeout_seconds=_require(d, "entry_timeout_seconds", "execution"),
        bracket_confirm_seconds=_require(d, "bracket_confirm_seconds", "execution"),
        slippage_ticks=_require(d, "slippage_ticks", "execution"),
    )


def _load_session(raw: dict) -> SessionCfg:
    d = _section(raw, "session")
    return SessionCfg(
        signal_staleness_seconds=_require(d, "signal_staleness_seconds", "session"),
        timezone=_require(d, "timezone", "session"),
        session_open_hour=_require(d, "session_open_hour", "session"),
        session_open_minute=_require(d, "session_open_minute", "session"),
        session_close_hour=_require(d, "session_close_hour", "session"),
        session_close_minute=_require(d, "session_close_minute", "session"),
        entry_blackout_open_minutes=_require(d, "entry_blackout_open_minutes", "session"),
        entry_blackout_close_minutes=_require(d, "entry_blackout_close_minutes", "session"),
        session_end_liquidation_hour=_require(d, "session_end_liquidation_hour", "session"),
        session_end_liquidation_minute=_require(d, "session_end_liquidation_minute", "session"),
        presession_check_hour=_require(d, "presession_check_hour", "session"),
        presession_check_minute=_require(d, "presession_check_minute", "session"),
        news_blackout_minutes=_require(d, "news_blackout_minutes", "session"),
    )


def _load_regime(raw: dict) -> RegimeCfg:
    d = _section(raw, "regime")
    return RegimeCfg(
        regime_refresh_minutes=_require(d, "regime_refresh_minutes", "regime"),
        poll_interval_sec=_require(d, "poll_interval_sec", "regime"),
    )


def _load_calendar(raw: dict) -> CalendarCfg:
    d = _section(raw, "calendar")
    return CalendarCfg(
        api_url=_require(d, "api_url", "calendar"),
        cache_hours=_require(d, "cache_hours", "calendar"),
    )


def _load_doctrine(raw: dict) -> DoctrineCfg:
    d = _section(raw, "doctrine")
    cfg = DoctrineCfg(
        edge_warning_win_rate=_dec(d, "edge_warning_win_rate", "doctrine"),
        edge_reduction_win_rate=_dec(d, "edge_reduction_win_rate", "doctrine"),
        edge_suspension_win_rate=_dec(d, "edge_suspension_win_rate", "doctrine"),
        edge_reduction_consecutive_weeks=_require(d, "edge_reduction_consecutive_weeks", "doctrine"),
        rolling_window_trades=_require(d, "rolling_window_trades", "doctrine"),
        risk_adjusted_window_trades=_require(d, "risk_adjusted_window_trades", "doctrine"),
        hypothetical_lookback_minutes=_require(d, "hypothetical_lookback_minutes", "doctrine"),
        hypothetical_price_window_minutes=_require(d, "hypothetical_price_window_minutes", "doctrine"),
    )
    if not (
        Decimal("0")
        < cfg.edge_suspension_win_rate
        < cfg.edge_reduction_win_rate
        < cfg.edge_warning_win_rate
        < Decimal("1")
    ):
        raise ConfigError(
            "doctrine win-rate thresholds must satisfy 0 < suspension < reduction < warning < 1"
        )
    return cfg


def load_config(path: Path) -> AppConfig:
    """Load and validate config from a YAML file. Strategy project supplies the path."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError(f"config.yaml did not parse as a mapping: {path}")
    return AppConfig(
        instrument=_load_instrument(raw),
        ibkr=_load_ibkr(raw),
        risk=_load_risk(raw),
        execution=_load_execution(raw),
        session=_load_session(raw),
        regime=_load_regime(raw),
        calendar=_load_calendar(raw),
        doctrine=_load_doctrine(raw),
    )
