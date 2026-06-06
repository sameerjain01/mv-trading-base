from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class TradingScheduler:
    """Thin wrapper around APScheduler's AsyncIOScheduler.

    Uses the existing asyncio event loop — never creates a new one.
    Silently no-ops if apscheduler is not installed (caller receives a warning).
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self._loop = loop or asyncio.get_event_loop()
        self._scheduler = None
        self._init_scheduler()

    def _init_scheduler(self) -> None:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            self._scheduler = AsyncIOScheduler(event_loop=self._loop)
            logger.debug("TradingScheduler: APScheduler initialized")
        except ImportError:
            logger.warning("apscheduler not installed — TradingScheduler is a no-op")

    def add_job(
        self,
        func: Callable,
        trigger: str,
        job_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        if self._scheduler is None:
            logger.warning("TradingScheduler.add_job: scheduler unavailable (apscheduler not installed)")
            return
        self._scheduler.add_job(func, trigger, id=job_id, **kwargs)
        logger.debug("TradingScheduler: job added", extra={"func": func.__name__, "trigger": trigger})

    def start(self) -> None:
        if self._scheduler is None:
            return
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("TradingScheduler: started")

    def stop(self) -> None:
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("TradingScheduler: stopped")
