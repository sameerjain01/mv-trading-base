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

## Critical Bugs (Found During mv-opt-one Paper Deployment — Fix Before Next Deploy)

### IBKRAdapter: all sync ib_async calls fail inside asyncio.run()

`IBKRAdapter` is declared async but internally uses synchronous `ib_async` methods
that call `loop.run_until_complete()`. When the entry point uses `asyncio.run()`,
any call to these sync methods raises `RuntimeError: This event loop is already running`.

**Broken methods and their fixes:**

| Method | Broken call | Fix |
|--------|-------------|-----|
| `connect()` | `ib.connect(...)` | `await ib.connectAsync(...)` |
| `reconcile_on_startup()` | `self._ib.reqAllOpenOrders()` | `await self._ib.reqAllOpenOrdersAsync()` |
| `reconcile_on_startup()` | `time.sleep(1)` | `await asyncio.sleep(1)` |
| `IBKRRegimeBroker.fetch_iv_history()` | `self._ib.reqHistoricalData(...)` | `await self._ib.reqHistoricalDataAsync(...)` |
| `IBKRRegimeBroker.get_bid_ask()` | `self._ib.reqTickers(contract)` | `await self._ib.reqTickersAsync(contract)` |
| `IBKRRegimeBroker.submit_put_spread()` | `self._ib.qualifyContracts(...)` | `await self._ib.qualifyContractsAsync(...)` |
| `IBKRRegimeBroker.submit_gtc_spread_close()` | `self._ib.qualifyContracts(...)` | `await self._ib.qualifyContractsAsync(...)` |
| `IBKRRegimeBroker.get_spread_mark()` | `self._ib.qualifyContracts(...)` + `reqTickers(...)` | async equivalents |
| `_prewarm_hmds()` | `self._ib.reqHistoricalData(...)` | `await reqHistoricalDataAsync(...)` or remove |

Data-read methods (`positions()`, `openTrades()`, `trades()`, `accountValues()`) return
cached subscription data without making new requests — these are fine to call sync.

**Workaround in place:** `IBKRRegimeBroker` in mv-opt-one overrides all affected methods
with async equivalents. Once trading_base ships the fix, delete those overrides.

---

### write_system_event: "message" is a reserved Python logging key

File: `trading_base/journal/writer.py`, line 148.

```python
# BROKEN — "message" overwrites LogRecord.message, raises KeyError
logger.info("System event written", extra={"event_type": event_type, "message": message})

# FIX — rename the key
logger.info("System event written", extra={"event_type": event_type, "event_msg": message})
```

**Workaround in place:** The installed package on the Hetzner server has been patched
in place (`sed` on the .py file). This patch will be lost if pip reinstalls trading_base.

---

## Future Features

| Feature | Notes |
|---|---|
| Position sizing with live equity | `PositionSizer` currently uses static equity input; live equity fetch from broker not wired |
| Regime persistence across restarts | `RegimeManager` loses state on restart; persist last known regime to state file |
| Journal GitHub push | Pattern implemented and confirmed working in mv-opt-one at `qqq_regime/journal/github_push.py`. Move to `trading_base/journal/github_push.py` when base lib async migration is complete. Requires GITHUB_PAT env var; reads GITHUB_REPO env var with a project-specific default. Silent on failure. |
| MV-AFTS async IBKR migration | `IBKRConnectionManager` is sync; `IBKRAdapter` is async. Full migration requires making `process_signal` async in MV-AFTS — reserved for a dedicated architectural task. Exception classes (`IBKRConnectionError`, `IBKRDataError`) already re-exported from trading_base as of trading-base-migration branch. |
