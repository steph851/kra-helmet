"""
WEB READER — read any URL and return structured content.
Used by monitors and action agents to fetch external pages.
Uses requests with session for browser-like behavior.
"""
import re
import time
import random
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class WebResult:
    url: str
    status_code: int
    content: str
    content_type: str
    elapsed_ms: int
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status_code < 400 and self.error is None

    @property
    def text(self) -> str:
        """Strip HTML tags and return plain text."""
        text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", self.content, flags=re.IGNORECASE)
        text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "status_code": self.status_code,
            "ok": self.ok,
            "content_type": self.content_type,
            "content_length": len(self.content),
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
        }


# Real browser User-Agents to rotate (avoids bot detection)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]


class WebReader:
    """Fetches URLs with session-based requests, retry, and browser-like headers."""

    def __init__(self, timeout: int = 20, max_retries: int = 2):
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy and browser-like defaults."""
        session = requests.Session()

        # Retry strategy for transient failures
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        })

        return session

    def _get_headers(self, url: str) -> dict[str, str]:
        """Generate browser-like headers for a specific URL."""
        # Extract domain for Referer
        domain_match = re.match(r"https?://([^/]+)", url)
        domain = domain_match.group(1) if domain_match else ""

        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Sec-Fetch-Site": "none" if "google" in url.lower() else "same-origin",
            "Referer": f"https://{domain}/",
        }

    def fetch(self, url: str, method: str = "GET") -> WebResult:
        """Fetch a URL using session-based requests. Returns WebResult with content or error."""
        last_error = None

        for attempt in range(self.max_retries + 1):
            start = time.monotonic()
            try:
                # Update headers for this request
                headers = self._get_headers(url)

                response = self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    timeout=self.timeout,
                    allow_redirects=True,
                )

                elapsed = int((time.monotonic() - start) * 1000)
                content_type = response.headers.get("Content-Type", "unknown")

                return WebResult(
                    url=url,
                    status_code=response.status_code,
                    content=response.text,
                    content_type=content_type,
                    elapsed_ms=elapsed,
                )

            except requests.exceptions.HTTPError as e:
                elapsed = int((time.monotonic() - start) * 1000)
                status_code = e.response.status_code if e.response is not None else 0
                body = e.response.text if e.response is not None else ""

                # If 403, try with different headers on retry
                if status_code == 403 and attempt < self.max_retries:
                    time.sleep(1 + random.random())  # Random delay
                    # Rotate User-Agent for retry
                    self._session.headers["User-Agent"] = random.choice(USER_AGENTS)
                    continue

                return WebResult(
                    url=url,
                    status_code=status_code,
                    content=body,
                    content_type="error",
                    elapsed_ms=elapsed,
                    error=str(e),
                )

            except requests.exceptions.RequestException as e:
                elapsed = int((time.monotonic() - start) * 1000)
                last_error = str(e)
                if attempt < self.max_retries:
                    time.sleep(1 + random.random())
                    continue

        return WebResult(
            url=url,
            status_code=0,
            content="",
            content_type="error",
            elapsed_ms=0,
            error=last_error or "Unknown error",
        )

    def ping(self, url: str) -> bool:
        """Quick HEAD check — returns True if reachable."""
        result = self.fetch(url, method="HEAD")
        return result.ok or result.status_code in (403, 405, 406)
