# mv-trading-base

Broker-agnostic, instrument-agnostic Python library for building algorithmic trading systems.
Used as the infrastructure layer for all MV trading projects.

Not a strategy. Not an executable. A foundation that strategies import.

---

## What's inside

| Module | Purpose |
|---|---|
| `timezone` | Market-time (ET) helpers, UTC conversion |
| `logging` | `setup_logging(log_file)`, `send_alert()` with optional SMTP |
| `constants` | `TradingMode`, `Regime`, `OrderState`, `RejectionCode`, `DegradationLevel`, `SignalAction`, `ExitReason` |
| `config` | `load_config(path) → AppConfig` — YAML-backed, no global singleton |
| `paths` | `paths_for(mode) → AppPaths` — consistent log/db/state dirs per mode |
| `cli` | `parse_mode()` — reads `--mode dev/paper/live` from argv |
| `models` | `Signal`, `Trade`, `Rejection`, `PositionRecord`, `OrderRecord`, `SubmissionResult`, `OrderStateMachine` |
| `risk` | `ConsecutiveLossTracker`, `EdgeDegradationDetector`, `PositionSizer` |
| `gates` | 11 pre-trade gate functions + `evaluate_all_gates()` orchestrator |
| `journal` | SQLite writer (`write_trade`, `write_rejection`), CSV export, Sharpe-equivalent metrics |
| `broker` | `BrokerAdapter` Protocol, `IBKRAdapter` (async), `MockBrokerAdapter` for tests |
| `execution` | `build_bracket_order(entry, stop, target, qty, instrument_cfg)` |
| `calendar` | `CalendarManager` — economic event fetch, high-impact blackout check |
| `regime` | `RegimeManager` — injectable classifier callable, TTL-based refresh |
| `scheduler` | APScheduler wrapper for daily resets and session timers |
| `webhook` | `create_app(signal_handler, broker, journal_path, expected_symbol) → FastAPI` |
| `data` | `IVRFetcher` — Implied Volatility Ratio (VIX/VIX3M) |

---

## Install

**Local development (editable):**
```bash
pip install -e /path/to/mv-trading-base
```

**As a git dependency in another project's `pyproject.toml`:**
```toml
dependencies = [
    "trading-base @ git+https://github.com/sameerjain01/mv-trading-base.git",
]
```

**Pinned to a tag:**
```toml
"trading-base @ git+https://github.com/sameerjain01/mv-trading-base.git@v0.1.0"
```

---

## Usage patterns

### Load config and initialize paths
```python
from trading_base.config import load_config
from trading_base.paths import paths_for
from trading_base.logging import setup_logging

cfg = load_config(Path("config.yaml"))
paths = paths_for(cfg.mode)
setup_logging(paths.log_file)
```

### Define an instrument and build a bracket order
```python
from decimal import Decimal
from trading_base.config import InstrumentCfg
from trading_base.execution import build_bracket_order

mes = InstrumentCfg(
    symbol="MES",
    exchange="CME",
    instrument_type="FUTURES",
    currency="USD",
    tick_size=Decimal("0.25"),
    point_value=Decimal("5"),
)

bracket = build_bracket_order(
    entry_price=Decimal("4500.00"),
    stop_price=Decimal("4490.00"),
    target_price=Decimal("4520.00"),
    quantity=2,
    instrument_cfg=mes,
)
```

### Run pre-trade gates
```python
from trading_base.gates import evaluate_all_gates

result = evaluate_all_gates(
    signal=signal,
    equity=equity,
    daily_pnl=daily_pnl,
    open_positions=positions,
    expected_symbol="MES",
    staleness_seconds=30,
    daily_loss_cap_pct=Decimal("0.02"),
    tick_size=mes.tick_size,
    spread=Decimal("0.25"),
    max_spread_ticks=2,
    current_price=Decimal("4500.00"),
    max_price_deviation_pct=Decimal("0.005"),
    current_time=datetime.now(tz=timezone.utc),
    session_start=time(18, 0),
    session_end=time(17, 0),
    events=calendar.fetch_today_events(),
    news_blackout_minutes=30,
    regime=regime,
    allowed_regimes={Regime.BULL, Regime.NEUTRAL},
    consecutive_loss_suspended=tracker.is_suspended(),
    degradation_level=detector.current_level(),
    mode=cfg.mode,
)

if not result.passed:
    # write rejection and return
```

### Connect an IBKR broker
```python
from trading_base.broker import IBKRAdapter

broker = IBKRAdapter(cfg.ibkr, cfg.mode, instrument_cfg=mes)
await broker.connect()
equity = await broker.get_account_equity()
```

### Use MockBrokerAdapter in tests
```python
from trading_base.broker import MockBrokerAdapter
from decimal import Decimal

broker = MockBrokerAdapter(responses={
    "get_account_equity": Decimal("50000"),
})
assert await broker.get_account_equity() == Decimal("50000")
assert ("get_account_equity", ()) in broker.calls["get_account_equity"]
```

---

## Design rules

**Decimal everywhere.** All financial values (`prices`, `pnl`, `equity`, `pct`) use `decimal.Decimal`. Never `float`. This is a hard constraint — float math on financial values causes silent precision loss.

**Mode gating.** `TradingMode` has three values: `DEV`, `PAPER`, `LIVE`. Code that touches a real broker is only reachable in `PAPER` or `LIVE`. In `DEV`, broker calls raise immediately. Spread and deviation gates pass in `DEV` without market data.

**No global config singleton.** Every entry point calls `load_config(path)` and threads the result through explicitly. No module-level `config` imports.

**BrokerAdapter is a Protocol.** `IBKRAdapter` and `MockBrokerAdapter` satisfy it structurally — no inheritance required. `isinstance(broker, BrokerAdapter)` works at runtime.

**Instance-level caching.** `CalendarManager` and `RegimeManager` cache on `self`, not on module globals. Each instance is independently testable and resettable.

---

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Slow tests (require a live IBKR paper account connection) are marked `@pytest.mark.slow` and skipped by default:
```bash
pytest -m slow
```

---

## config.yaml structure

```yaml
mode: paper

ibkr:
  host: 127.0.0.1
  port: 4002
  client_id: 1
  timeout_seconds: 10
  readonly: false

risk:
  max_daily_loss_pct: "0.02"
  max_position_size: 2
  consecutive_loss_threshold: 3
  cooldown_hours: 4
  min_equity: "5000"

doctrine:
  rolling_window_trades: 30
  warning_loss_rate: "0.40"
  reduction_loss_rate: "0.55"
  suspension_loss_rate: "0.70"

regime:
  regime_refresh_minutes: 5

webhook:
  port: 8000
  expected_symbol: "MES"

alerts:
  smtp_host: ""
  email_from: ""
  email_to: ""
```
