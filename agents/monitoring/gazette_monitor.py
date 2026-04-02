"""
GAZETTE MONITOR — watches Kenya Gazette for tax-related legal notices.
BOUNDARY: Fetches public gazette pages and flags tax-relevant notices.
Never interprets legal text — routes findings to human review.
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

# Kenya Gazette and legal sources with fallbacks
GAZETTE_SOURCES = [
    {
        "key": "kenya_gazette",
        "urls": [
            "https://www.kenyalaw.org/kenya_gazette/",
            "http://kenyalaw.org/kenya_gazette/",
            "https://kenyalaw.org/kl/index.php?id=96",
        ],
        "label": "Kenya Gazette",
        "watch_for": ["tax", "revenue", "KRA", "finance act", "finance bill",
                      "income tax", "value added tax", "excise duty",
                      "tax procedures", "NSSF", "NHIF", "SHIF", "SHA",
                      "housing levy", "turnover tax", "withholding tax"],
    },
    {
        "key": "kenya_law_acts",
        "urls": [
            "http://kenyalaw.org/kl/index.php?id=702",
            "https://www.kenyalaw.org/kl/index.php?id=702",
            "https://kenyalaw.org/kl/index.php?id=702",
        ],
        "label": "Kenya Law — Tax Acts",
        "watch_for": ["income tax act", "tax procedures act", "value added tax act",
                      "excise duty act", "finance act", "amendment"],
    },
    {
        "key": "parliament_bills",
        "urls": [
            "http://www.parliament.go.ke/the-national-assembly/house-business/bills",
            "https://www.parliament.go.ke/the-national-assembly/house-business/bills",
            "https://parliament.go.ke/the-national-assembly/house-business/bills",
        ],
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


class GazetteMonitor(BaseAgent):
    name = "gazette_monitor"
    boundary = "Fetches public gazette pages only. Never interprets legal text."

    def __init__(self):
        super().__init__()
        self._state_file = self.data_dir / "monitoring" / "gazette_state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"pages": {}, "notices": []}

    def _save_state(self):
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self.save_json(self._state_file, self._state)

    def scan(self) -> list[dict]:
        """Scan gazette sources for tax-related changes. Returns list of findings."""
        findings = []

        for source in GAZETTE_SOURCES:
            result = self._check_source(source)
            if result:
                findings.append(result)

        if findings:
            self.log(f"Detected {len(findings)} gazette finding(s)")
            for finding in findings:
                self._route_to_review(finding)
        else:
            self.log("No gazette changes detected")

        self._state["last_scan"] = datetime.now(EAT).isoformat()
        self._save_state()
        return findings

    def _check_source(self, source: dict) -> dict | None:
        """Fetch a gazette page, check for content changes and tax-relevant patterns."""
        key = source["key"]
        urls = source["urls"]

        content = self._fetch_with_fallback(urls)
        if content is None:
            self.log(f"Failed to fetch {key} from all sources", "WARN")
            return None

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        prev_hash = self._state["pages"].get(key, {}).get("hash")

        # Baseline — first time
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
            "url": urls[0],
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
        self.write_staging("review", filename, review_item)
        self.log(f"Routed gazette finding to review: {filename}")

    def get_state(self) -> dict:
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
