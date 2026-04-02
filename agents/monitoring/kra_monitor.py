"""
KRA MONITOR — watches for KRA announcements, rate changes, and deadline updates.
BOUNDARY: Fetches and parses public KRA pages. Flags changes for human review.
Never auto-applies rate or deadline changes — routes to staging/review.
"""
import json
import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..base import BaseAgent
import sys
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
from tools.web_reader import WebReader

EAT = timezone(timedelta(hours=3))

# KRA pages to monitor with fallback sources
KRA_SOURCES = [
    {
        "key": "kra_notices",
        "urls": [
            "https://www.kra.go.ke/news-center/public-notices",
            "https://kra.go.ke/news-center/public-notices",
            "https://www.kra.go.ke/announcements",
        ],
        "label": "KRA Public Notices",
        "watch_for": ["tax rate", "deadline", "penalty", "filing", "extension",
                      "turnover tax", "VAT", "PAYE", "withholding", "etims",
                      "income tax", "finance act", "tax amendment"],
    },
    {
        "key": "kra_deadlines",
        "urls": [
            "https://www.kra.go.ke/individual/filing-paying/filing-deadlines",
            "https://kra.go.ke/individual/filing-paying/filing-deadlines",
            "https://www.kra.go.ke/deadlines",
        ],
        "label": "KRA Filing Deadlines",
        "watch_for": ["deadline", "extension", "postpone", "new date"],
    },
    {
        "key": "kra_rates",
        "urls": [
            "https://www.kra.go.ke/individual/filing-paying/types-of-taxes",
            "https://kra.go.ke/individual/filing-paying/types-of-taxes",
            "https://www.kra.go.ke/tax-rates",
        ],
        "label": "KRA Tax Rates",
        "watch_for": ["rate", "percentage", "threshold", "bracket", "turnover"],
    },
]


class KRAMonitor(BaseAgent):
    name = "kra_monitor"
    boundary = "Fetches public KRA pages and detects changes. Never auto-applies changes."

    def __init__(self):
        super().__init__()
        self._state_file = self.data_dir / "monitoring" / "kra_state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        """Load previous page hashes and last-seen timestamps."""
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"pages": {}, "alerts": []}

    def _save_state(self):
        """Persist state to disk."""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self.save_json(self._state_file, self._state)

    def scan(self) -> list[dict]:
        """Scan all KRA sources for changes. Returns list of detected changes."""
        changes = []

        for source in KRA_SOURCES:
            result = self._check_source(source)
            if result:
                changes.append(result)

        if changes:
            self.log(f"Detected {len(changes)} KRA change(s)")
            for change in changes:
                # Route to human review
                self._route_to_review(change)
        else:
            self.log("No KRA changes detected")

        self._state["last_scan"] = datetime.now(EAT).isoformat()
        self._save_state()
        return changes

    def _check_source(self, source: dict) -> dict | None:
        """Fetch a page and check if content has changed."""
        key = source["key"]
        urls = source["urls"]

        content = self._fetch_with_fallback(urls)
        if content is None:
            self.log(f"Failed to fetch {key} from all sources", "WARN")
            return None

        # Hash the content
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        prev_hash = self._state["pages"].get(key, {}).get("hash")

        # First time seeing this page — record baseline
        if prev_hash is None:
            self._state["pages"][key] = {
                "hash": content_hash,
                "last_checked": datetime.now(EAT).isoformat(),
                "last_changed": None,
            }
            self.log(f"Baseline recorded for {key}")
            return None

        # No change
        if content_hash == prev_hash:
            self._state["pages"][key]["last_checked"] = datetime.now(EAT).isoformat()
            return None

        # Change detected — extract relevant keywords
        keywords_found = self._extract_keywords(content, source.get("watch_for", []))

        change = {
            "source": key,
            "label": source["label"],
            "url": urls[0],
            "change_type": "content_changed",
            "keywords_found": keywords_found,
            "previous_hash": prev_hash,
            "new_hash": content_hash,
            "detected_at": datetime.now(EAT).isoformat(),
            "content_snippet": self._extract_snippet(content, keywords_found),
        }

        # Update state
        self._state["pages"][key] = {
            "hash": content_hash,
            "last_checked": datetime.now(EAT).isoformat(),
            "last_changed": datetime.now(EAT).isoformat(),
        }
        self._state["alerts"].append({
            "source": key,
            "detected_at": change["detected_at"],
            "keywords": keywords_found,
        })
        # Keep last 50 alerts
        self._state["alerts"] = self._state["alerts"][-50:]

        return change

    def _fetch_with_fallback(self, urls: list[str]) -> str | None:
        """Try fetching from multiple URLs, return first successful result."""
        reader = WebReader(timeout=20, max_retries=2)

        for url in urls:
            result = reader.fetch(url)
            if result.ok:
                self.log(f"Successfully fetched from {url}")
                return result.content
            self.log(f"Failed to fetch {url}: {result.error}", "WARN")

        return None

    def _extract_keywords(self, content: str, watch_for: list[str]) -> list[str]:
        """Find which watched keywords appear in the content."""
        content_lower = content.lower()
        return [kw for kw in watch_for if kw.lower() in content_lower]

    def _extract_snippet(self, content: str, keywords: list[str], max_length: int = 300) -> str:
        """Extract a text snippet around the first keyword found."""
        # Strip HTML tags for readable text
        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"\s+", " ", text).strip()

        if not keywords:
            return text[:max_length]

        # Find first keyword occurrence and extract surrounding context
        text_lower = text.lower()
        for kw in keywords:
            idx = text_lower.find(kw.lower())
            if idx >= 0:
                start = max(0, idx - 100)
                end = min(len(text), idx + len(kw) + 200)
                snippet = text[start:end].strip()
                if start > 0:
                    snippet = "..." + snippet
                if end < len(text):
                    snippet = snippet + "..."
                return snippet

        return text[:max_length]

    def _route_to_review(self, change: dict):
        """Route a detected change to human review via staging."""
        review_item = {
            "type": "kra_change_detected",
            "source": change["source"],
            "label": change["label"],
            "url": change["url"],
            "keywords": change["keywords_found"],
            "snippet": change["content_snippet"],
            "detected_at": change["detected_at"],
            "status": "pending_review",
            "action_needed": "Review KRA page for tax rate, deadline, or policy changes",
        }

        ts = datetime.now(EAT).strftime("%Y%m%d_%H%M%S")
        filename = f"kra_change_{change['source']}_{ts}.json"
        self.write_staging("review", filename, review_item)
        self.log(f"Routed KRA change to review: {filename}")

    def get_state(self) -> dict:
        """Return current monitoring state."""
        return {
            "sources_tracked": len(self._state.get("pages", {})),
            "last_scan": self._state.get("last_scan"),
            "recent_alerts": self._state.get("alerts", [])[-5:],
            "pages": {
                k: {
                    "last_checked": v.get("last_checked"),
                    "last_changed": v.get("last_changed"),
                }
                for k, v in self._state.get("pages", {}).items()
            },
        }
