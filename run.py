"""
KRA Deadline Tracker — CLI Entry Point
Usage:
    python run.py onboard              → Interactive SME onboarding
    python run.py import <csv_file>    → Batch import SMEs from CSV
    python run.py import --template    → Generate CSV template
    python run.py check <PIN>          → Full compliance check for one SME
    python run.py check --all          → Check all onboarded SMEs
    python run.py file <PIN>           → Record a tax filing (interactive)
    python run.py file <PIN> <tax> <period> [amount] [ref]
    python run.py filings <PIN>        → View filing history
    python run.py status               → System status dashboard
    python run.py review               → Human gate — review pending items
    python run.py audit [PIN]          → View audit trail
    python run.py guide <tax_type>     → Show filing guide for a tax type
    python run.py guide --list         → List available filing guides
    python run.py report <PIN>         → Generate per-SME HTML report
    python run.py report --all         → Generate reports for all SMEs
    python run.py dashboard            → Generate HTML dashboard
    python run.py pulse                → Start The Pulse (background scheduler)
    python run.py pulse --once         → Run one scheduler tick
    python run.py pulse --status       → Show scheduler status
    python run.py pulse --trigger PIN  → Trigger immediate check for one SME
    python run.py pulse --trigger-all  → Trigger check for all SMEs
    python run.py eyes                 → Run full monitoring scan (The Eyes)
    python run.py eyes --health        → Source health check only
    python run.py eyes --kra           → Scan KRA announcements only
    python run.py eyes --gazette       → Scan Kenya Gazette only
    python run.py eyes --etims [PIN]   → Check eTIMS compliance
    python run.py eyes --status        → Show monitoring status
    python run.py actions <PIN>        → Show "do this now" action list
    python run.py prepare <PIN> [tax]  → Prepare filing package
    python run.py deliver              → Deliver pending alerts
    python run.py escalate             → Run escalation check for all SMEs
    python run.py brain                → Run full Brain analysis (patterns + feedback)
    python run.py brain --patterns     → Mine compliance patterns only
    python run.py brain --feedback     → Run feedback loop only
    python run.py brain --propose      → Propose risk model weight update
    python run.py brain --status       → Show model updater status
    python run.py brain --ingest       → Ingest audit trail + filing history
    python run.py brain --timeline PIN → Show SME compliance timeline
    python run.py api                  → Start REST API server
    python run.py demo                 → Onboard a demo SME and run full check
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

# Ensure project root is on path
sys.path.insert(0, str(ROOT))

from agents.orchestrator import Orchestrator
from workflow.human_gate import HumanGate
from workflow.audit_trail import AuditTrail


BANNER = """
╔═══════════════════════════════════════════════════════╗
║  🛡️  KRA Deadline Tracker — Tax Compliance Autopilot  v1.0     ║
║  Protecting Kenyan SMEs from tax penalties            ║
╚═══════════════════════════════════════════════════════╝"""


def main():
    print(BANNER)

    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()
    args = sys.argv[2:]
    orch = Orchestrator()

    if command == "onboard":
        profile = orch.onboard(interactive=True)
        if profile:
            print(f"\n✅ Onboarded: {profile['name']} (PIN: {profile['pin']})")
            print(f"   Industry: {profile['classification']['industry_label']}")
            print(f"   Obligations: {', '.join(profile['classification']['obligations'])}")
            print(f"\n   Run 'python run.py check {profile['pin']}' to see compliance status.\n")

    elif command == "check":
        if args and args[0] == "--all":
            results = orch.check_all()
            print(f"\n{'='*60}")
            print(f"  Checked {len(results)} SME(s)")
            for r in results:
                p = r["profile"]
                c = r["compliance"]
                rsk = r["risk"]
                urg = r["urgency"]
                print(f"  {urg['emoji']} {p['name']} — {c['overall']} | risk={rsk['risk_score']}")
            print()
        elif args:
            pin = args[0].upper()
            result = orch.check_sme(pin)
            if result:
                print(f"\n{'='*60}")
                print(result["message"])
                print(f"{'='*60}\n")

                urg = result["urgency"]
                pen = result.get("penalties", {})
                if pen.get("total_penalty_exposure_kes", 0) > 0:
                    print(f"  Penalty exposure: KES {pen['total_penalty_exposure_kes']:,.0f} ({pen['severity']})")
                if urg["should_alert"]:
                    print(f"  {urg['emoji']} {urg['prefix']}: Alert would be sent via {result['profile'].get('preferred_channel', 'whatsapp')}")
                if result.get("alerts_queued", 0) > 0:
                    print(f"  Alerts queued: {result['alerts_queued']}")
                print()
            else:
                print(f"\n  SME not found: {pin}")
                print(f"  Run 'python run.py onboard' first.\n")
        else:
            print("  Usage: python run.py check <PIN> or python run.py check --all")

    elif command == "status":
        orch.status()

    elif command == "review":
        gate = HumanGate()
        gate.interactive_review()

    elif command == "audit":
        trail = AuditTrail()
        pin = args[0].upper() if args else None
        trail.print_history(sme_pin=pin)

    elif command == "guide":
        import json
        guides_path = ROOT / "intelligence" / "filing_guides.json"
        guides = json.loads(guides_path.read_text(encoding="utf-8"))

        if not args or args[0] == "--list":
            print(f"\n{'='*60}")
            print(f"  Available Filing Guides")
            print(f"{'='*60}")
            for g in guides["filing_guides"]:
                print(f"  {g['tax_key']:30s} — {g['title']}")
            print(f"\n  Usage: python run.py guide <tax_key>\n")
        else:
            tax_key = args[0].lower()
            guide = next((g for g in guides["filing_guides"] if g["tax_key"] == tax_key), None)
            if not guide:
                print(f"\n  Guide not found: {tax_key}")
                print(f"  Run 'python run.py guide --list' to see available guides.\n")
            else:
                print(f"\n{'='*60}")
                print(f"  {guide['title']}")
                print(f"  iTax path: {guide['itax_menu_path']}")
                print(f"  Estimated time: {guide['estimated_time']}")
                print(f"{'='*60}")
                print(f"\n  Documents needed:")
                for d in guide["documents_needed"]:
                    print(f"    • {d}")
                print(f"\n  Steps:")
                for i, step in enumerate(guide["steps"], 1):
                    print(f"    {i:2d}. {step}")
                print(f"\n  Common mistakes:")
                for m in guide["common_mistakes"]:
                    print(f"    ⚠ {m}")
                print(f"\n  Tips:")
                for t in guide["tips"]:
                    print(f"    💡 {t}")
                print()

    elif command == "import":
        from agents.onboarding.batch_onboarder import BatchOnboarder
        batch = BatchOnboarder()

        if args and args[0] == "--template":
            output = ROOT / "sme_template.csv"
            batch.generate_template(output)
            print(f"\n  CSV template generated: {output}")
            print(f"  Fill it in and run: python run.py import sme_template.csv\n")
        elif args:
            results = batch.import_csv(args[0])
            print(f"\n{'='*60}")
            print(f"  Batch Import Results")
            print(f"{'='*60}")
            print(f"  Imported: {results['success']}")
            print(f"  Skipped:  {results['skipped']} (already onboarded)")
            print(f"  Failed:   {results['failed']}")
            if results["errors"]:
                print(f"\n  Errors:")
                for e in results["errors"]:
                    print(f"    - {e}")
            if results["imported"]:
                print(f"\n  New SMEs:")
                for s in results["imported"]:
                    print(f"    + {s['name']} ({s['pin']})")
            print()
        else:
            print("  Usage: python run.py import <csv_file> or python run.py import --template")

    elif command == "file":
        from workflow.filing_tracker import FilingTracker
        tracker = FilingTracker()

        if not args:
            print("  Usage: python run.py file <PIN> [tax_type] [period] [amount] [reference]")
        elif len(args) == 1:
            # Interactive mode
            tracker.interactive_file(args[0].upper())
        else:
            # Direct mode: file PIN tax_type period [amount] [ref]
            pin = args[0].upper()
            tax_type = args[1]
            period = args[2] if len(args) > 2 else ""
            amount = float(args[3]) if len(args) > 3 else 0
            ref = args[4] if len(args) > 4 else ""

            if not period:
                print("  Usage: python run.py file <PIN> <tax_type> <period> [amount] [reference]")
            else:
                tracker.record_filing(pin, tax_type, period, amount, ref)

    elif command == "filings":
        from workflow.filing_tracker import FilingTracker
        tracker = FilingTracker()
        pin = args[0].upper() if args else None
        if not pin:
            print("  Usage: python run.py filings <PIN>")
        else:
            tracker.print_history(pin)

    elif command == "report":
        from agents.report_generator import ReportGenerator
        gen = ReportGenerator()

        if args and args[0] == "--all":
            paths = gen.generate_all()
            print(f"\n  Generated {len(paths)} report(s):")
            for p in paths:
                print(f"    {p}")
            print()
        elif args:
            pin = args[0].upper()
            path = gen.generate(pin)
            if path:
                print(f"\n  Report generated: {path}\n")
            else:
                print(f"\n  SME not found: {pin}\n")
        else:
            print("  Usage: python run.py report <PIN> or python run.py report --all")

    elif command == "dashboard":
        from agents.dashboard import DashboardGenerator
        gen = DashboardGenerator()
        output = gen.generate()
        print(f"\n  Dashboard generated: {output}\n")

    elif command == "pulse":
        if args and args[0] == "--once":
            from scheduler.heartbeat import Heartbeat
            pulse = Heartbeat()
            result = pulse.run_once()
            pulse.print_status()
        elif args and args[0] == "--status":
            from scheduler.heartbeat import Heartbeat
            pulse = Heartbeat()
            pulse.print_status()
        elif args and args[0] == "--trigger" and len(args) > 1:
            from scheduler.heartbeat import Heartbeat
            pulse = Heartbeat()
            pin = args[1].upper()
            reason = args[2] if len(args) > 2 else "manual_cli"
            if pulse.trigger_check(pin, reason):
                print(f"\n  Queued check for {pin}")
                result = pulse.trigger.dispatch_next()
                if result:
                    print(f"  Result: {result.get('compliance', {}).get('overall', '?')}\n")
            else:
                print(f"\n  {pin} already in queue\n")
        elif args and args[0] == "--trigger-all":
            from scheduler.heartbeat import Heartbeat
            pulse = Heartbeat()
            count = pulse.trigger_all(reason="cli_batch")
            print(f"\n  Queued {count} SME(s) for check")
            results = pulse.trigger.dispatch_batch()
            print(f"  Dispatched {len(results)} check(s)\n")
        else:
            from scheduler.heartbeat import run_pulse
            run_pulse()

    elif command == "eyes":
        from agents.monitoring import MonitoringOrchestrator
        monitor = MonitoringOrchestrator()

        if args and args[0] == "--health":
            monitor.health.print_status()
        elif args and args[0] == "--kra":
            changes = monitor.run_kra_only()
            print(f"\n  KRA scan complete: {len(changes)} change(s) detected\n")
            for c in changes:
                print(f"    [{c['source']}] {', '.join(c.get('keywords_found', []))}")
        elif args and args[0] == "--gazette":
            findings = monitor.run_gazette_only()
            print(f"\n  Gazette scan complete: {len(findings)} finding(s)\n")
            for f in findings:
                print(f"    [{f['source']}] {', '.join(f.get('keywords_found', []))}")
        elif args and args[0] == "--etims":
            if len(args) > 1:
                pin = args[1].upper()
                result = monitor.check_etims_sme(pin)
                print(f"\n  eTIMS check for {pin}: {result.get('status', 'unknown')}")
                for issue in result.get("issues", []):
                    print(f"    - {issue}")
                print()
            else:
                issues = monitor.run_etims_only()
                print(f"\n  eTIMS scan complete: {len(issues)} issue(s)\n")
                for i in issues:
                    print(f"    {i['pin']} ({i['name']}): {i['issue_count']} issue(s)")
        elif args and args[0] == "--status":
            monitor.print_status()
        else:
            print("\n  Running full monitoring scan...\n")
            results = monitor.run_full_scan()
            s = results["summary"]
            print(f"\n  {'='*50}")
            print(f"  THE EYES — Scan Complete")
            print(f"  {'='*50}")
            print(f"  Sources: {s['sources_healthy']}")
            print(f"  KRA changes: {results['kra_changes']}")
            print(f"  Gazette findings: {results['gazette_findings']}")
            print(f"  eTIMS issues: {results['etims_issues']}")
            print(f"  Total findings: {s['total_findings']}")
            print()

    elif command == "actions":
        from agents.action import RecommendationEngine
        rec = RecommendationEngine()
        if args:
            pin = args[0].upper()
            rec.print_recommendations(pin)
        else:
            print("  Usage: python run.py actions <PIN>")

    elif command == "prepare":
        from agents.action import WorkflowEngine
        wf = WorkflowEngine()
        if not args:
            print("  Usage: python run.py prepare <PIN> [tax_type]")
        elif len(args) >= 2:
            pin = args[0].upper()
            tax_type = args[1].lower()
            package = wf.prepare_filing(pin, tax_type)
            if package:
                wf.print_package(package)
            else:
                print(f"\n  Failed to prepare filing for {pin} / {tax_type}\n")
        else:
            pin = args[0].upper()
            packages = wf.prepare_all_due(pin)
            if packages:
                print(f"\n  Prepared {len(packages)} filing package(s):")
                for pkg in packages:
                    print(f"    {pkg['tax_type']} — period {pkg['period']}")
                print(f"\n  Run 'python run.py prepare {pin} <tax_type>' for details.\n")
            else:
                print(f"\n  No due filings found for {pin}\n")

    elif command == "deliver":
        from agents.action import AlertEngine
        engine = AlertEngine()
        results = engine.process_queue()
        print(f"\n  Delivered {len(results)} alert(s)")
        for r in results:
            print(f"    [{r.get('status', '?')}] {r.get('alert_file', '?')}")
        print()

    elif command == "escalate":
        from agents.action import EscalationEngine
        engine = EscalationEngine()
        escalations = engine.evaluate_all()
        print(f"\n  {'='*50}")
        print(f"  ESCALATION CHECK — {len(escalations)} item(s)")
        print(f"  {'='*50}")
        for esc in escalations:
            tier = esc["tier"].upper()
            print(f"  [{tier}] {esc['pin']} — {esc['reason']}")
        if not escalations:
            print("  All clear — no escalations needed.")
        print()

    elif command == "brain":
        from agents.learning import DecisionMemory, PatternMiner, FeedbackLoop, ModelUpdater

        if args and args[0] == "--patterns":
            miner = PatternMiner()
            miner.print_report()
        elif args and args[0] == "--feedback":
            loop = FeedbackLoop()
            loop.print_report()
        elif args and args[0] == "--propose":
            updater = ModelUpdater()
            proposal = updater.propose_update()
            print(f"\n  Proposal created: {len(proposal.get('adjustments', []))} adjustment(s)")
            for reason in proposal.get("reasoning", []):
                print(f"    {reason}")
            print(f"\n  Review in staging/review/ before applying.\n")
        elif args and args[0] == "--status":
            updater = ModelUpdater()
            updater.print_status()
        elif args and args[0] == "--ingest":
            memory = DecisionMemory()
            audit_count = memory.ingest_audit_trail()
            filing_count = memory.ingest_filing_history()
            print(f"\n  Ingested {audit_count} audit entries + {filing_count} filing records\n")
        elif args and args[0] == "--timeline" and len(args) > 1:
            memory = DecisionMemory()
            pin = args[1].upper()
            timeline = memory.sme_timeline(pin)
            print(f"\n{'='*60}")
            print(f"  Timeline for {pin}")
            print(f"{'='*60}")
            if timeline:
                for t in timeline:
                    outcome = f" → {t['outcome']}" if t.get("outcome") else ""
                    print(f"  {t['timestamp'][:16]}  {t['event']:20s} {t['detail']}{outcome}")
            else:
                print("  No decision history found.")
            print()
        else:
            print("\n  Running full Brain analysis...\n")
            # Ingest first
            memory = DecisionMemory()
            audit_count = memory.ingest_audit_trail()
            filing_count = memory.ingest_filing_history()
            print(f"  Ingested: {audit_count} audit + {filing_count} filing records")

            # Patterns
            miner = PatternMiner()
            miner.print_report()

            # Feedback
            loop = FeedbackLoop()
            loop.print_report()

            # Summary
            summary = memory.summary()
            print(f"\n  Decision Memory: {summary['total_entries']} entries, "
                  f"{summary['sme_count']} SMEs, "
                  f"{summary['outcome_rate']*100:.0f}% with outcomes\n")

    elif command == "api":
        print("\n  Starting KRA Deadline Tracker API server...")
        print("  Open http://localhost:8000 in your browser")
        print("  API docs: http://localhost:8000/docs\n")
        import subprocess
        try:
            subprocess.run([sys.executable, "-m", "uvicorn", "api:app", "--reload", "--port", "8000"], cwd=str(ROOT))
        except KeyboardInterrupt:
            pass  # Clean shutdown via Ctrl+C

    elif command == "demo":
        print("\n  Running demo with test SME...\n")
        demo_data = {
            "pin": "A000000001B",
            "name": "Brian Ochieng",
            "business_name": "Brian's Electronics",
            "business_type": "sole_proprietor",
            "industry": "retail_wholesale",
            "county": "Nairobi",
            "annual_turnover_kes": 3500000,
            "turnover_bracket": "1m_to_8m",
            "has_employees": True,
            "employee_count": 2,
            "is_vat_registered": False,
            "has_etims": False,
            "phone": "0712345678",
            "preferred_language": "en",
            "preferred_channel": "whatsapp",
        }

        # Onboard
        profile = orch.onboard(interactive=False, data=demo_data)
        if not profile:
            print("  Demo onboarding failed.")
            return

        print(f"  ✅ Onboarded: {profile['name']} (PIN: {profile['pin']})")
        print(f"     Industry: {profile['classification']['industry_label']}")
        print(f"     Obligations: {', '.join(profile['classification']['obligations'])}")

        # Check
        print(f"\n  Running compliance check...\n")
        result = orch.check_sme(profile["pin"])
        if result:
            print(f"{'='*60}")
            print(result["message"])
            print(f"{'='*60}")
            urg = result["urgency"]
            print(f"\n  {urg['emoji']} Urgency: {urg['prefix']}")
            print(f"  Alert channel: {profile.get('preferred_channel', 'whatsapp')}")
            print()

    else:
        print(f"  Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
