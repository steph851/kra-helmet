"""
SOURCE HEALTH — checks if external data sources are reachable.
BOUNDARY: Only pings endpoints. Never scrapes content or stores data.
"""
import urllib.request
import urllib.error
import ssl
import time
from datetime import datetime, timedelta, timezone

from ..base import BaseAgent

EAT = timezone(timedelta(hours=3))

# Known sources and their health-check URLs
SOURCES = {
    "kra_website": {
        "url": "https://www.kra.go.ke",
        "label": "KRA Main Website",
        "timeout": 15,
    },
    "itax_portal": {
        "url": "https://itax.kra.go.ke",
        "label": "iTax Portal",
        "timeout": 15,
    },
    "etims_portal": {
        "url": "https://etims.kra.go.ke",
        "label": "eTIMS Portal",
        "timeout": 15,
    },
    "kenya_gazette": {
        "url": "https://www.kenyalaw.org",
        "label": "Kenya Law / Gazette",
        "timeout": 15,
    },
    "nssf_portal": {
        "url": "https://www.nssf.or.ke",
        "label": "NSSF Portal",
        "timeout": 15,
    },
    "shif_portal": {
        "url": "https://www.sha.go.ke",
        "label": "SHA (SHIF) Portal",
        "timeout": 15,
    },
}


class SourceHealth(BaseAgent):
    name = "source_health"
    boundary = "Pings endpoints only. Never scrapes or stores external content."

    def __init__(self):
        super().__init__()
        self._history: list[dict] = []

    def check_source(self, source_key: str) -> dict:
        """Check if a single source is reachable. Returns health result dict."""
        source = SOURCES.get(source_key)
        if not source:
            return {
                "source": source_key,
                "status": "unknown",
                "error": f"Unknown source: {source_key}",
                "checked_at": datetime.now(EAT).isoformat(),
            }

        url = source["url"]
        timeout = source.get("timeout", 15)
        start = time.monotonic()

        try:
            # Create SSL context that doesn't verify (some .go.ke certs are flaky)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "KRA-Helmet-HealthCheck/1.0")

            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                status_code = resp.status
                elapsed_ms = int((time.monotonic() - start) * 1000)

                return {
                    "source": source_key,
                    "label": source["label"],
                    "url": url,
                    "status": "up" if status_code < 400 else "degraded",
                    "status_code": status_code,
                    "response_ms": elapsed_ms,
                    "checked_at": datetime.now(EAT).isoformat(),
                }

        except urllib.error.HTTPError as e:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            # Some sites block HEAD but are still "up"
            return {
                "source": source_key,
                "label": source["label"],
                "url": url,
                "status": "up" if e.code in (403, 405, 406) else "degraded",
                "status_code": e.code,
                "response_ms": elapsed_ms,
                "note": "Blocked HEAD request but site is reachable" if e.code in (403, 405, 406) else str(e),
                "checked_at": datetime.now(EAT).isoformat(),
            }

        except (urllib.error.URLError, OSError, TimeoutError) as e:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {
                "source": source_key,
                "label": source["label"],
                "url": url,
                "status": "down",
                "error": str(e),
                "response_ms": elapsed_ms,
                "checked_at": datetime.now(EAT).isoformat(),
            }

    def check_all(self) -> dict:
        """Check all known sources. Returns summary with per-source results."""
        results = {}
        for key in SOURCES:
            results[key] = self.check_source(key)

        up_count = sum(1 for r in results.values() if r["status"] == "up")
        down_count = sum(1 for r in results.values() if r["status"] == "down")
        degraded_count = sum(1 for r in results.values() if r["status"] == "degraded")

        summary = {
            "overall": "healthy" if down_count == 0 else ("degraded" if up_count > 0 else "down"),
            "total": len(results),
            "up": up_count,
            "down": down_count,
            "degraded": degraded_count,
            "checked_at": datetime.now(EAT).isoformat(),
            "sources": results,
        }

        # Record in history
        self._history.append({
            "overall": summary["overall"],
            "up": up_count,
            "down": down_count,
            "checked_at": summary["checked_at"],
        })
        # Keep last 100 entries
        self._history = self._history[-100:]

        self.log(f"Source health: {up_count} up, {down_count} down, {degraded_count} degraded")
        return summary

    def get_history(self) -> list[dict]:
        """Return recent health check history."""
        return list(self._history)

    def print_status(self):
        """Print source health to console."""
        results = self.check_all()
        print(f"\n{'='*65}")
        print(f"  THE EYES — Source Health Check")
        print(f"  {datetime.now(EAT).strftime('%Y-%m-%d %H:%M:%S')} EAT")
        print(f"{'='*65}")
        print(f"  Overall: {results['overall'].upper()}")
        print(f"  Up: {results['up']}  Down: {results['down']}  Degraded: {results['degraded']}")
        print()

        for key, r in results["sources"].items():
            status = r["status"].upper()
            ms = r.get("response_ms", "?")
            icon = {"up": "+", "down": "X", "degraded": "!"}
            marker = icon.get(r["status"], "?")
            print(f"  [{marker}] {r.get('label', key):30s} {status:10s} {ms}ms")
            if r.get("error"):
                print(f"      Error: {r['error'][:80]}")
            if r.get("note"):
                print(f"      Note: {r['note']}")
        print()
