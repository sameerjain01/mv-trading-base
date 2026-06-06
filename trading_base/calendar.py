from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date as DateType
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from trading_base.config import CalendarCfg

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EconomicEvent:
    name: str
    event_time: datetime

    def __post_init__(self) -> None:
        if self.event_time.tzinfo is None:
            raise ValueError(
                f"EconomicEvent.event_time must be timezone-aware, got naive: {self.event_time}"
            )


class CalendarManager:
    """Fetches and caches high-impact US economic events for today.

    Requires env var CALENDAR_API_KEY for Finnhub free tier.
    Returns empty list (not None) when API key absent or API fails — callers
    treat missing events as safe (no blackout). gate_news_blackout treats None
    (unavailable) differently from [] (no events today).
    """

    def __init__(self, cfg: "CalendarCfg") -> None:
        self._cfg = cfg
        self._cache: dict[DateType, Optional[list[EconomicEvent]]] = {}

    def fetch_today_events(self) -> Optional[list[EconomicEvent]]:
        """Return today's high-impact events, or None if API call failed.

        None signals that the calendar is unavailable. gate_news_blackout
        should fail-safe when it receives None.
        """
        today = datetime.now(timezone.utc).date()
        if today in self._cache:
            logger.debug("Economic calendar cache hit", extra={"date": str(today)})
            return self._cache[today]

        result = self._fetch_from_api(today)
        self._cache[today] = result
        return result

    def has_high_impact_event(
        self,
        current_time: datetime,
        window_minutes: int,
    ) -> bool:
        """True if any high-impact event is within window_minutes of current_time."""
        events = self.fetch_today_events()
        if events is None:
            return True  # fail-safe: assume blackout when calendar unavailable
        blackout_seconds = window_minutes * 60
        for event in events:
            if abs((current_time - event.event_time).total_seconds()) <= blackout_seconds:
                return True
        return False

    def _fetch_from_api(self, today: DateType) -> Optional[list[EconomicEvent]]:
        if httpx is None:
            logger.warning("httpx not installed — economic calendar unavailable")
            return None

        api_key = os.environ.get("CALENDAR_API_KEY", "")
        today_str = today.isoformat()
        params: dict[str, str] = {"from": today_str, "to": today_str}
        if api_key:
            params["token"] = api_key
        else:
            logger.warning("CALENDAR_API_KEY not set — economic calendar unavailable")
            return None

        try:
            response = httpx.get(self._cfg.api_url, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.warning("Economic calendar API failed", extra={"error": str(exc)})
            return None

        if isinstance(data, dict):
            items = data.get("economicCalendar", [])
        elif isinstance(data, list):
            items = data
        else:
            logger.warning("Calendar API: unexpected response shape", extra={"type": type(data).__name__})
            return None

        events: list[EconomicEvent] = []
        for item in items:
            try:
                if item.get("country", "").upper() not in ("US", "USA", "UNITED STATES", ""):
                    continue
                if item.get("impact", "").lower() != "high":
                    continue
                name = item.get("event") or item.get("category") or "Unknown"
                time_str = item.get("time") or item.get("Date") or ""
                if not time_str:
                    continue
                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt.date() != today:
                    continue
                events.append(EconomicEvent(name=name, event_time=dt))
            except Exception as exc:
                logger.debug("Skipping malformed calendar event", extra={"error": str(exc)})
                continue

        logger.info(
            "Economic calendar fetched",
            extra={"date": str(today), "high_impact_count": len(events)},
        )
        return events
