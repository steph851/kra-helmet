"""
BASE INTEGRATION — hardened integration layer with rate limiting, retry, and timeout.
BOUNDARY: Provides common integration patterns. Never stores sensitive data.
"""
import time
import functools
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from collections import defaultdict
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

EAT = timezone(timedelta(hours=3))


class RateLimiter:
    """Token bucket rate limiter per endpoint."""

    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.calls: list[datetime] = []

    def wait_if_needed(self):
        """Wait if rate limit would be exceeded."""
        now = datetime.now(EAT)
        # Remove calls older than 1 minute
        self.calls = [c for c in self.calls if now - c < timedelta(minutes=1)]

        if len(self.calls) >= self.calls_per_minute:
            # Wait until oldest call is more than 1 minute old
            wait_time = 60 - (now - self.calls[0]).total_seconds()
            if wait_time > 0:
                time.sleep(wait_time)

        self.calls.append(now)


class IntegrationConfig:
    """Configuration for hardened integrations."""

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
        rate_limit_calls: int = 60,
        rate_limit_period: int = 60,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.retry_backoff = retry_backoff
        self.rate_limit_calls = rate_limit_calls
        self.rate_limit_period = rate_limit_period


class HardenedIntegration:
    """Base class for all hardened integrations."""

    def __init__(self, config: IntegrationConfig | None = None):
        self.config = config or IntegrationConfig()
        self.rate_limiter = RateLimiter(self.config.rate_limit_calls)
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy."""
        session = requests.Session()

        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.retry_backoff,
            status_forcelist=[429, 500, 502, 503, 504],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> requests.Response:
        """Make a hardened HTTP request with rate limiting and timeout."""
        self.rate_limiter.wait_if_needed()

        kwargs.setdefault("timeout", self.config.timeout)

        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()

        return response

    def get(self, url: str, **kwargs) -> requests.Response:
        """Make a hardened GET request."""
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        """Make a hardened POST request."""
        return self.request("POST", url, **kwargs)


def with_retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Decorator for retry logic with exponential backoff."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        raise

            raise last_exception
        return wrapper
    return decorator


def with_timeout(timeout: int = 30):
    """Decorator for timeout control."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError(f"Operation timed out after {timeout} seconds")

            # Set the signal handler
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)

            try:
                result = func(*args, **kwargs)
                signal.alarm(0)  # Cancel the alarm
                return result
            finally:
                signal.signal(signal.SIGALRM, old_handler)

        return wrapper
    return decorator
