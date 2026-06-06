from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Optional

from trading_base.constants import Regime

if TYPE_CHECKING:
    from trading_base.broker.protocol import BrokerAdapter
    from trading_base.config import RegimeCfg

logger = logging.getLogger(__name__)


class RegimeManager:
    """Polls broker for bar data and classifies regime via an injectable classifier.

    The classifier is strategy-supplied:
        def my_classifier(bars: list) -> Regime: ...

    trading-base supplies only the polling shell — no regime logic lives here.
    """

    def __init__(
        self,
        broker: "BrokerAdapter",
        classifier: Callable,
        cfg: "RegimeCfg",
        symbol: str,
        bar_duration: str = "1 D",
        bar_size: str = "1 day",
        bar_count: int = 20,
    ) -> None:
        self._broker = broker
        self._classifier = classifier
        self._cfg = cfg
        self._symbol = symbol
        self._bar_duration = bar_duration
        self._bar_size = bar_size
        self._bar_count = bar_count
        self._current_regime: Regime = Regime.UNKNOWN
        self._last_updated: Optional[datetime] = None
        self._last_refresh: float = 0.0

    def current_regime(self) -> Regime:
        return self._current_regime

    def last_updated(self) -> Optional[datetime]:
        return self._last_updated

    async def refresh(self) -> None:
        now = time.monotonic()
        ttl = self._cfg.regime_refresh_minutes * 60
        if now - self._last_refresh < ttl:
            return

        try:
            from trading_base.data.ivr import calculate_ivr  # noqa: F401 — ensure data module importable

            # Attempt to get historical bars via broker adapter
            # The BrokerAdapter protocol doesn't have get_historical_bars yet;
            # this is a shell — real bar fetching depends on IBKRAdapter internals.
            # Strategy may override by providing a custom broker that returns bars.
            bars = await self._get_bars()
        except Exception as exc:
            logger.error("RegimeManager.refresh: bar fetch failed — setting UNKNOWN", extra={"error": str(exc)})
            self._current_regime = Regime.UNKNOWN
            self._last_updated = datetime.now(timezone.utc)
            return

        try:
            new_regime = self._classifier(bars)
        except Exception as exc:
            logger.error("RegimeManager.refresh: classifier failed — setting UNKNOWN", extra={"error": str(exc)})
            self._current_regime = Regime.UNKNOWN
            self._last_updated = datetime.now(timezone.utc)
            return

        if new_regime != self._current_regime:
            logger.info(
                "Regime changed",
                extra={"from": self._current_regime.value, "to": new_regime.value},
            )

        self._current_regime = new_regime
        self._last_updated = datetime.now(timezone.utc)
        self._last_refresh = now

    async def _get_bars(self) -> list:
        """Return bars from broker. Subclasses or strategies may override.

        Default implementation works with IBKRAdapter which exposes the
        synchronous _ib handle. Injected brokers that implement get_historical_bars
        are called here if available.
        """
        adapter = self._broker
        if hasattr(adapter, "_ib") and adapter._ib is not None:
            from trading_base.broker.ibkr import IBKRAdapter
            if isinstance(adapter, IBKRAdapter):
                contract = IBKRAdapter._build_contract(adapter._instrument_cfg)
                raw = adapter._ib.reqHistoricalData(
                    contract,
                    endDateTime="",
                    durationStr=self._bar_duration,
                    barSizeSetting=self._bar_size,
                    whatToShow="TRADES",
                    useRTH=True,
                    formatDate=1,
                    keepUpToDate=False,
                )
                return raw[-self._bar_count:] if raw else []
        logger.debug("RegimeManager: no bar source — returning empty list")
        return []
