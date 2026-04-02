"""
AGENT CALLER — agent-to-agent communication bus.
Allows any agent to invoke another agent's methods without tight coupling.
Provides a registry pattern for loose coupling between subsystems.
"""
from datetime import datetime
from pathlib import Path

import sys
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


class AgentCaller:
    """Central bus for agent-to-agent calls. Lazy-loads agents on first use."""

    def __init__(self):
        self._registry: dict[str, object] = {}
        self._call_log: list[dict] = []

    def _get_agent(self, agent_name: str):
        """Lazy-load and cache agent instances."""
        if agent_name not in self._registry:
            agent = self._resolve_agent(agent_name)
            if agent:
                self._registry[agent_name] = agent
        return self._registry.get(agent_name)

    def _resolve_agent(self, name: str):
        """Resolve agent name to instance. Returns None if unknown."""
        try:
            if name == "orchestrator":
                from agents.orchestrator import Orchestrator
                return Orchestrator()
            elif name == "notification_engine":
                from agents.communication import NotificationEngine
                return NotificationEngine()
            elif name == "urgency_framer":
                from agents.communication import UrgencyFramer
                return UrgencyFramer()
            elif name == "explainer":
                from agents.communication import Explainer
                return Explainer()
            elif name == "risk_scorer":
                from agents.intelligence import RiskScorer
                return RiskScorer()
            elif name == "compliance_checker":
                from agents.intelligence import ComplianceChecker
                return ComplianceChecker()
            elif name == "penalty_calculator":
                from agents.intelligence import PenaltyCalculator
                return PenaltyCalculator()
            elif name == "obligation_mapper":
                from agents.intelligence import ObligationMapper
                return ObligationMapper()
            elif name == "deadline_calculator":
                from agents.intelligence import DeadlineCalculator
                return DeadlineCalculator()
            elif name == "monitoring":
                from agents.monitoring import MonitoringOrchestrator
                return MonitoringOrchestrator()
            elif name == "input_validator":
                from agents.validation.input_validator import InputValidator
                return InputValidator()
            elif name == "dashboard":
                from agents.dashboard import DashboardGenerator
                return DashboardGenerator()
            elif name == "report_generator":
                from agents.report_generator import ReportGenerator
                return ReportGenerator()
        except ImportError:
            pass
        return None

    def call(self, agent_name: str, method: str, *args, **kwargs):
        """Call a method on a named agent. Returns result or raises."""
        agent = self._get_agent(agent_name)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_name}")

        fn = getattr(agent, method, None)
        if fn is None or not callable(fn):
            raise ValueError(f"Agent '{agent_name}' has no method '{method}'")

        # Log the call
        self._call_log.append({
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "method": method,
            "args_count": len(args),
            "kwargs_keys": list(kwargs.keys()),
        })

        return fn(*args, **kwargs)

    def has_agent(self, agent_name: str) -> bool:
        """Check if an agent is available."""
        return self._resolve_agent(agent_name) is not None

    def list_agents(self) -> list[str]:
        """List all known agent names."""
        return [
            "orchestrator", "notification_engine", "urgency_framer", "explainer",
            "risk_scorer", "compliance_checker", "penalty_calculator",
            "obligation_mapper", "deadline_calculator", "monitoring",
            "input_validator", "dashboard", "report_generator",
        ]

    def get_call_log(self, limit: int = 50) -> list[dict]:
        """Return recent agent-to-agent calls."""
        return self._call_log[-limit:]
