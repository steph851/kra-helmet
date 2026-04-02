"""
GAZETTE CONNECTOR — Kenya Gazette monitoring for tax-related notices.
BOUNDARY: Fetches public gazette pages and flags tax-relevant notices.
Never interprets legal text — routes findings to human review.
"""
import json
import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools.web_reader import WebReader

EAT = timezone(timedelta(hours=3))

# Kenya Gazette and legal sources
GAZETTE_SOURCES = [
    {
        "key": "kenya_gazette",
        "url": "http://kenyalaw.org/kenya_gazette/",
        "label": "Kenya Gazette",
        "watch_for": ["tax", "revenue", "KRA", "finance act", "finance bill",
                      "income tax", "value added tax", "excise duty",
                      "tax procedures", "NSSF", "NHIF", "SHIF", "SHA",
                      "housing levy", "turnover tax", "withholding tax"],
    },
    {
        "key": "kenya_law_acts",
        "url": "http://kenyalaw.org/kl/index.php?id=702",
        "label": "Kenya Law — Tax Acts",
        "watch_for": ["income tax act", "tax procedures act", "value added tax act",
                      "excise duty act", "finance act", "amendment"],
    },
    {
        "key": "parliament_bills",
        "url": "http://www.parliament.go.ke/the-national-assembly/house-business/bills",
        "label": "Parliament — Bills",
        "watch_for": ["finance bill", "tax", "revenue", "amendment"],
    },
]

# Tax-related gazette notice patterns
TAX_PATTERNS = [
    r"(?i)legal\s+notice\s+no\.?\s*\d+.*?(?:tax|revenue|KRA|duty|levy)",
    r"(?i)(?:finance|tax)\s+(?:act|bill|amendment)\s+\d{4}",
    r"(?i)(?:effective|commence|operation)\s+(?:date|from)\s+\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+\d{4}",
    r"(?i)gazette\s+notice\s+no\.?\s*\d+",
    r"(?i)(?:increase|decrease|change|revise|amend).*?(?:rate|tax|duty|threshold|penalty)",
]


class GazetteConnector:
    """Kenya Gazette monitoring for tax-related legal notices."""

    def __init__(self):
        self.reader = WebReader(timeout=20, max_retries=3)
        self._state_path = ROOT / "data" / "monitoring" / "gazette_state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        """Load gazette monitoring state."""
        if self._state_path.exists():
            try:
                return json.loads(self._state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"pages": {}, "notices": []}

    def _save_state(self):
        """Save gazette monitoring state."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(self._state, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def scan(self) -> list[dict]:
        """Scan gazette sources for tax-related changes."""
        findings = []

        for source in GAZETTE_SOURCES:
            result = self._check_source(source)
            if result:
                findings.append(result)

        if findings:
            for finding in findings:
                self._route_to_review(finding)

        self._state["last_scan"] = datetime.now(EAT).isoformat()
        self._save_state()
        return findings

    def _check_source(self, source: dict) -> dict | None:
        """Fetch a gazette page, check for content changes and tax-relevant patterns."""
        key = source["key"]
        url = source["url"]

        result = self.reader.fetch(url)
        if not result.ok:
            return None

        content = result.content
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        prev_hash = self._state["pages"].get(key, {}).get("hash")

        # Baseline — first time
        if prev_hash is None:
            self._state["pages"][key] = {
                "hash": content_hash,
                "last_checked": datetime.now(EAT).isoformat(),
                "last_changed": None,
            }
            return None

        # No change
        if content_hash == prev_hash:
            self._state["pages"][key]["last_checked"] = datetime.now(EAT).isoformat()
            return None

        # Change detected — look for tax-relevant patterns
        keywords_found = self._extract_keywords(content, source.get("watch_for", []))
        legal_notices = self._extract_legal_notices(content)

        if not keywords_found and not legal_notices:
            # Content changed but nothing tax-related — update hash silently
            self._state["pages"][key] = {
                "hash": content_hash,
                "last_checked": datetime.now(EAT).isoformat(),
                "last_changed": datetime.now(EAT).isoformat(),
            }
            return None

        finding = {
            "source": key,
            "label": source["label"],
            "url": url,
            "change_type": "gazette_update",
            "keywords_found": keywords_found,
            "legal_notices": legal_notices,
            "previous_hash": prev_hash,
            "new_hash": content_hash,
            "detected_at": datetime.now(EAT).isoformat(),
        }

        # Update state
        self._state["pages"][key] = {
            "hash": content_hash,
            "last_checked": datetime.now(EAT).isoformat(),
            "last_changed": datetime.now(EAT).isoformat(),
        }
        self._state["notices"].append({
            "source": key,
            "detected_at": finding["detected_at"],
            "keywords": keywords_found,
            "notice_count": len(legal_notices),
        })
        self._state["notices"] = self._state["notices"][-50:]

        return finding

    def _extract_keywords(self, content: str, watch_for: list[str]) -> list[str]:
        """Find which watched keywords appear in the content."""
        content_lower = content.lower()
        return [kw for kw in watch_for if kw.lower() in content_lower]

    def _extract_legal_notices(self, content: str) -> list[str]:
        """Extract legal notice references that match tax-related patterns."""
        # Strip HTML
        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"\s+", " ", text)

        notices = []
        for pattern in TAX_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                cleaned = match.strip()
                if cleaned and cleaned not in notices and len(cleaned) < 200:
                    notices.append(cleaned)

        return notices[:20]  # cap at 20

    def _route_to_review(self, finding: dict):
        """Route gazette finding to human review."""
        review_dir = ROOT / "staging" / "review"
        review_dir.mkdir(parents=True, exist_ok=True)

        review_item = {
            "type": "gazette_change_detected",
            "source": finding["source"],
            "label": finding["label"],
            "url": finding["url"],
            "keywords": finding["keywords_found"],
            "legal_notices": finding["legal_notices"],
            "detected_at": finding["detected_at"],
            "status": "pending_review",
            "action_needed": "Review gazette for new tax legislation, rate changes, or deadline amendments",
            "impact": "May require updates to tax_knowledge_graph.json or deadline_calendar.json",
        }

        ts = datetime.now(EAT).strftime("%Y%m%d_%H%M%S")
        filename = f"gazette_{finding['source']}_{ts}.json"
        review_path = review_dir / filename
        review_path.write_text(
            json.dumps(review_item, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def get_state(self) -> dict:
        """Get current gazette monitoring state."""
        return {
            "sources_tracked": len(self._state.get("pages", {})),
            "last_scan": self._state.get("last_scan"),
            "recent_notices": self._state.get("notices", [])[-5:],
            "pages": {
                k: {
                    "last_checked": v.get("last_checked"),
                    "last_changed": v.get("last_changed"),
                }
                for k, v in self._state.get("pages", {}).items()
            },
        }

    def get_sources(self) -> list[dict]:
        """Get list of monitored gazette sources."""
        return GAZETTE_SOURCES
