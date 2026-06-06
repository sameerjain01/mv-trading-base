from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = timezone.utc


class MarketTime:
    def __init__(self, service_tz: timezone = UTC, market_tz: str | ZoneInfo = ET) -> None:
        self.service_tz = service_tz
        self.market_tz = ZoneInfo(market_tz) if isinstance(market_tz, str) else market_tz

    def now(self) -> datetime:
        return datetime.now(self.service_tz)

    def now_et(self) -> datetime:
        return datetime.now(self.market_tz)

    def to_et(self, dt: datetime) -> datetime:
        return dt.astimezone(self.market_tz)

    def et_wall(self, d: date, t: time) -> datetime:
        """ET wall-clock → service-tz datetime. DST-aware: 10:30 ET → 14:30 UTC (EDT) or 15:30 UTC (EST)."""
        return datetime.combine(d, t, tzinfo=self.market_tz).astimezone(self.service_tz)
