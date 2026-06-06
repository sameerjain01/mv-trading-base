# Backlog

Tracked gaps and future work for mv-trading-base.

---

## Test Coverage Gaps

Modules extracted from MV-AFTS with no unit tests yet.
Not blocking migration — the logic was validated in paper trading.
Fill these in as modules are touched during active development.

| Module | Test file to add | Notes |
|---|---|---|
| `trading_base/timezone.py` | `tests/test_timezone.py` | MarketTime wrapping, ET/UTC conversion |
| `trading_base/paths.py` | `tests/test_paths.py` | paths_for(mode) returns correct dirs per mode |
| `trading_base/calendar.py` | `tests/test_calendar.py` | CalendarManager fetch, cache, blackout logic; mock HTTP |
| `trading_base/regime.py` | `tests/test_regime.py` | RegimeManager with injectable classifier, TTL refresh |
| `trading_base/scheduler.py` | `tests/test_scheduler.py` | Job scheduling and cancellation |
| `trading_base/webhook/receiver.py` | `tests/test_webhook.py` | FastAPI app creation, signal validation, HMAC rejection |
| `trading_base/models/order_state.py` | `tests/test_order_state.py` | Full OrderStateMachine transition coverage |

---

## Future Features

| Feature | Notes |
|---|---|
| Position sizing with live equity | `PositionSizer` currently uses static equity input; live equity fetch from broker not wired |
| Regime persistence across restarts | `RegimeManager` loses state on restart; persist last known regime to state file |
| Journal GitHub push | Moved out of MV-AFTS into base if pattern is reused by other strategies |
| MV-AFTS async IBKR migration | `IBKRConnectionManager` is sync; `IBKRAdapter` is async. Full migration requires making `process_signal` async in MV-AFTS — reserved for a dedicated architectural task. Exception classes (`IBKRConnectionError`, `IBKRDataError`) already re-exported from trading_base as of trading-base-migration branch. |
