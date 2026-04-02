"""
MONITORING ORCHESTRATOR — coordinates all monitors.
BOUNDARY: Dispatches monitors and aggregates results. Never modifies tax data directly.
All changes route through human review (staging/review/).
"""
import json
from datetime import datetime, timedelta, timezone

from ..base import BaseAgent
from .kra_monitor import KRAMonitor
from .gazette_monitor import GazetteMonitor
from .etims_monitor import EtimsMonitor
from .source_health import SourceHealth

import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
from workflow.audit_trail import AuditTrail

EAT = timezone(timedelta(hours=3))


class MonitoringOrchestrator(BaseAgent):
    name = "monitoring_orchestrator"
    boundary = "Coordinates monitors. Never modifies tax data — all changes route to human review."

    def __init__(self):
        super().__init__()
        self.kra = KRAMonitor()
        self.gazette = GazetteMonitor()
        self.etims = EtimsMonitor()
        self.health = SourceHealth()
        self.audit = AuditTrail()

    def run_full_scan(self) -> dict:
        """Run all monitors. Returns aggregated results."""
        self.log("=== THE EYES — Full Scan Start ===")
        results = {}

        # 1. Source health check
        self.log("Checking source health...")
        results["source_health"] = self.safe_run(
            lambda: self.health.check_all(),
            context="source_health",
            fallback={"overall": "unknown", "error": "health check failed"},
        )

        # 2. KRA announcements
        self.log("Scanning KRA announcements...")
        kra_changes = self.safe_run(
            lambda: self.kra.scan(),
            context="kra_monitor",
            fallback=[],
        )
        results["kra_changes"] = len(kra_changes)
        results["kra_details"] = kra_changes

        # 3. Kenya Gazette
        self.log("Scanning Kenya Gazette...")
        gazette_findings = self.safe_run(
            lambda: self.gazette.scan(),
            context="gazette_monitor",
            fallback=[],
        )
        results["gazette_findings"] = len(gazette_findings)
        results["gazette_details"] = gazette_findings

        # 4. eTIMS compliance
        self.log("Checking eTIMS compliance...")
        etims_issues = self.safe_run(
            lambda: self.etims.scan(),
            context="etims_monitor",
            fallback=[],
        )
        results["etims_issues"] = len(etims_issues)
        results["etims_details"] = etims_issues

        # Summary
        total_findings = results["kra_changes"] + results["gazette_findings"] + results["etims_issues"]
        results["summary"] = {
            "total_findings": total_findings,
            "sources_healthy": results["source_health"].get("overall", "unknown"),
            "scanned_at": datetime.now(EAT).isoformat(),
        }

        # Audit
        self.audit.record("MONITORING_SCAN", self.name, {
            "kra_changes": results["kra_changes"],
            "gazette_findings": results["gazette_findings"],
            "etims_issues": results["etims_issues"],
            "sources_status": results["source_health"].get("overall", "unknown"),
        })

        self.log(
            f"=== THE EYES — Scan Complete: "
            f"{total_findings} finding(s), "
            f"sources {results['source_health'].get('overall', '?')} ==="
        )

        return results

    def run_health_only(self) -> dict:
        """Quick source health check only."""
        return self.health.check_all()

    def run_kra_only(self) -> list[dict]:
        """Scan KRA only."""
        return self.kra.scan()

    def run_gazette_only(self) -> list[dict]:
        """Scan gazette only."""
        return self.gazette.scan()

    def run_etims_only(self) -> list[dict]:
        """Scan eTIMS only."""
        return self.etims.scan()

    def check_etims_sme(self, pin: str) -> dict:
        """Check eTIMS compliance for a single SME."""
        return self.etims.check_sme(pin)

    def status(self) -> dict:
        """Full monitoring status across all monitors."""
        return {
            "kra": self.kra.get_state(),
            "gazette": self.gazette.get_state(),
            "etims": self.etims.get_state(),
            "source_health_history": self.health.get_history()[-5:],
            "last_full_scan": self.audit.get_history(limit=1),
        }

    def print_status(self):
        """Print monitoring status to console."""
        print(f"\n{'='*65}")
        print(f"  THE EYES — Monitoring Status")
        print(f"  {datetime.now(EAT).strftime('%Y-%m-%d %H:%M:%S')} EAT")
        print(f"{'='*65}")

        # KRA
        kra = self.kra.get_state()
        print(f"\n  KRA Monitor:")
        print(f"    Sources tracked: {kra['sources_tracked']}")
        print(f"    Last scan: {kra.get('last_scan', 'never')}")
        if kra.get("recent_alerts"):
            print(f"    Recent alerts: {len(kra['recent_alerts'])}")

        # Gazette
        gaz = self.gazette.get_state()
        print(f"\n  Gazette Monitor:")
        print(f"    Sources tracked: {gaz['sources_tracked']}")
        print(f"    Last scan: {gaz.get('last_scan', 'never')}")
        if gaz.get("recent_notices"):
            print(f"    Recent notices: {len(gaz['recent_notices'])}")

        # eTIMS
        etims = self.etims.get_state()
        print(f"\n  eTIMS Monitor:")
        print(f"    SMEs tracked: {etims['smes_tracked']}")
        print(f"    Compliant: {etims['compliant']}")
        print(f"    Non-compliant: {etims['non_compliant']}")
        print(f"    Last scan: {etims.get('last_scan', 'never')}")

        print()
