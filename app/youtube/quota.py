"""YouTube API Quota Tracker.

Tracks API usage to help manage daily quota limits (default 10,000 units/day).
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)


class QuotaTracker:
    """Track YouTube API quota usage.
    
    YouTube Data API has a daily quota limit (default 10,000 units).
    Different operations have different costs:
    - videos.insert: 1600 units
    - videos.list: 1 unit
    - search.list: 100 units
    - playlistItems.list: 1 unit
    - channels.list: 1 unit
    """

    # API operation costs in quota units
    QUOTA_COSTS = {
        "videos.insert": 1600,
        "videos.list": 1,
        "videos.update": 50,
        "videos.delete": 50,
        "search.list": 100,
        "playlistItems.list": 1,
        "channels.list": 1,
    }

    # Default daily quota limit
    DEFAULT_DAILY_LIMIT = 10_000

    def __init__(self, daily_limit: int = DEFAULT_DAILY_LIMIT) -> None:
        """Initialize quota tracker.
        
        Args:
            daily_limit: Daily quota limit (default 10,000)
        """
        self._daily_limit = daily_limit
        self._usage: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._lock = Lock()
        self._reset_date: datetime | None = None

    def _get_today_key(self) -> str:
        """Get today's date key in PST (YouTube quota resets at midnight PST)."""
        # YouTube quota resets at midnight Pacific Time
        # Approximate by using UTC-8
        now = datetime.now(UTC) - timedelta(hours=8)
        return now.strftime("%Y-%m-%d")

    def _check_reset(self) -> None:
        """Check if daily quota should be reset."""
        today = self._get_today_key()
        if self._reset_date != today:
            with self._lock:
                if self._reset_date != today:
                    # Keep only today's usage
                    if today not in self._usage:
                        self._usage = defaultdict(lambda: defaultdict(int))
                    self._reset_date = today
                    logger.info("Quota tracker reset for new day: %s", today)

    def track(self, operation: str, count: int = 1) -> int:
        """Track an API operation.
        
        Args:
            operation: API operation name (e.g., "videos.list")
            count: Number of times the operation was called
            
        Returns:
            Cost in quota units
        """
        self._check_reset()
        
        cost = self.QUOTA_COSTS.get(operation, 1) * count
        today = self._get_today_key()
        
        with self._lock:
            self._usage[today][operation] += count
        
        logger.debug(
            "API call: %s x%d = %d units (total today: %d)",
            operation,
            count,
            cost,
            self.get_daily_usage(),
        )
        
        return cost

    def get_daily_usage(self) -> int:
        """Get today's total quota usage.
        
        Returns:
            Total units used today
        """
        self._check_reset()
        today = self._get_today_key()
        
        total = 0
        with self._lock:
            for op, count in self._usage.get(today, {}).items():
                total += self.QUOTA_COSTS.get(op, 1) * count
        
        return total

    def get_remaining_quota(self) -> int:
        """Get remaining quota for today.
        
        Returns:
            Estimated remaining units
        """
        return max(0, self._daily_limit - self.get_daily_usage())

    def get_usage_summary(self) -> dict:
        """Get detailed usage summary.
        
        Returns:
            Dict with usage breakdown
        """
        self._check_reset()
        today = self._get_today_key()
        
        with self._lock:
            today_usage = dict(self._usage.get(today, {}))
        
        breakdown = {}
        total = 0
        for op, count in today_usage.items():
            cost = self.QUOTA_COSTS.get(op, 1) * count
            breakdown[op] = {
                "calls": count,
                "cost_per_call": self.QUOTA_COSTS.get(op, 1),
                "total_cost": cost,
            }
            total += cost
        
        return {
            "date": today,
            "total_used": total,
            "daily_limit": self._daily_limit,
            "remaining": max(0, self._daily_limit - total),
            "usage_percentage": round(total / self._daily_limit * 100, 2),
            "breakdown": breakdown,
        }

    def can_perform(self, operation: str, count: int = 1) -> bool:
        """Check if an operation can be performed within quota.
        
        Args:
            operation: API operation name
            count: Number of times to perform
            
        Returns:
            True if sufficient quota remains
        """
        cost = self.QUOTA_COSTS.get(operation, 1) * count
        return self.get_remaining_quota() >= cost


# Module-level singleton
_quota_tracker: QuotaTracker | None = None


def get_quota_tracker() -> QuotaTracker:
    """Get or create quota tracker singleton.
    
    Returns:
        QuotaTracker instance
    """
    global _quota_tracker
    if _quota_tracker is None:
        _quota_tracker = QuotaTracker()
    return _quota_tracker
