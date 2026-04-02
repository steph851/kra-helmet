"""
EVENT LISTENER — webhook handler for external events.
Receives signals from iTax, payment systems, or manual triggers
and pushes them into the priority queue for immediate processing.
"""
import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from .priority_queue import PriorityQueue


# ── Request Models ──────────────────────────────────────────────

class FilingEvent(BaseModel):
    pin: str
    tax_type: str
    period: str
    source: str = "external"

    model_config = {
        "json_schema_extra": {
            "examples": [{"pin": "A000000001B", "tax_type": "vat", "period": "2026-03", "source": "itax"}]
        }
    }


class SMEUpdateEvent(BaseModel):
    pin: str
    fields_changed: list[str] = []
    source: str = "external"

    model_config = {
        "json_schema_extra": {
            "examples": [{"pin": "A000000001B", "fields_changed": ["annual_turnover_kes", "has_employees"], "source": "admin"}]
        }
    }


class ManualTrigger(BaseModel):
    pin: str | None = None
    check_all: bool = False
    reason: str = "manual"

    model_config = {
        "json_schema_extra": {
            "examples": [{"pin": "A000000001B", "reason": "deadline approaching"}]
        }
    }


class ScheduleOverride(BaseModel):
    pin: str
    urgency_level: str = "red"
    reason: str = "priority_override"

    model_config = {
        "json_schema_extra": {
            "examples": [{"pin": "A000000001B", "urgency_level": "red", "reason": "KRA audit notice received"}]
        }
    }


# ── Webhook Router ──────────────────────────────────────────────

def create_webhook_router(queue: PriorityQueue, trigger_engine=None) -> APIRouter:
    """Create FastAPI router for webhook endpoints."""

    router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
    WEBHOOK_SECRET = os.getenv("HELMET_WEBHOOK_SECRET", "")

    def _verify_signature(x_webhook_secret: str | None):
        if WEBHOOK_SECRET and x_webhook_secret != WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    @router.post("/filing", summary="New filing recorded")
    def on_filing(event: FilingEvent, x_webhook_secret: str | None = Header(None)):
        """External system reports a new filing — triggers re-check to update compliance status."""
        _verify_signature(x_webhook_secret)

        added = queue.push(
            pin=event.pin,
            urgency_level="orange",
            reason=f"filing_reported:{event.tax_type}:{event.period}",
        )

        return {
            "accepted": True,
            "queued": added,
            "pin": event.pin,
            "message": f"Re-check queued for {event.pin}" if added else f"{event.pin} already in queue",
            "timestamp": datetime.now().isoformat(),
        }

    @router.post("/sme-update", summary="SME profile updated")
    def on_sme_update(event: SMEUpdateEvent, x_webhook_secret: str | None = Header(None)):
        """SME profile changed — re-check may discover new obligations."""
        _verify_signature(x_webhook_secret)

        added = queue.push(
            pin=event.pin,
            urgency_level="orange",
            reason=f"profile_updated:{','.join(event.fields_changed)}",
        )

        return {
            "accepted": True,
            "queued": added,
            "pin": event.pin,
            "fields_changed": event.fields_changed,
            "timestamp": datetime.now().isoformat(),
        }

    @router.post("/trigger", summary="Manual check trigger")
    def on_trigger(event: ManualTrigger, x_webhook_secret: str | None = Header(None)):
        """Manually trigger a compliance check for one or all SMEs."""
        _verify_signature(x_webhook_secret)

        if event.check_all and trigger_engine:
            count = trigger_engine.trigger_all(reason=event.reason)
            return {
                "accepted": True,
                "queued": count,
                "mode": "batch",
                "reason": event.reason,
                "timestamp": datetime.now().isoformat(),
            }

        if not event.pin:
            raise HTTPException(status_code=400, detail="Provide pin or set check_all=true")

        added = queue.push(
            pin=event.pin,
            urgency_level="red",
            reason=f"manual:{event.reason}",
        )

        return {
            "accepted": True,
            "queued": added,
            "pin": event.pin,
            "reason": event.reason,
            "timestamp": datetime.now().isoformat(),
        }

    @router.post("/priority-override", summary="Override check priority")
    def on_priority_override(event: ScheduleOverride, x_webhook_secret: str | None = Header(None)):
        """Push an SME to the front of the queue with elevated priority."""
        _verify_signature(x_webhook_secret)

        # Remove existing entry (if any) and re-add at higher priority
        queue.remove(event.pin)
        added = queue.push(
            pin=event.pin,
            urgency_level=event.urgency_level,
            reason=event.reason,
        )

        return {
            "accepted": True,
            "queued": added,
            "pin": event.pin,
            "urgency_level": event.urgency_level,
            "reason": event.reason,
            "timestamp": datetime.now().isoformat(),
        }

    @router.get("/queue", summary="View queue status")
    def get_queue_status():
        """View current priority queue contents and stats."""
        return {
            "stats": queue.stats(),
            "tasks": queue.list_tasks(),
            "timestamp": datetime.now().isoformat(),
        }

    return router
