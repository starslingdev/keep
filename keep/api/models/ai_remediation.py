from typing import Optional
from uuid import UUID

from pydantic import BaseModel, root_validator


class AIRemediationRequest(BaseModel):
    """Request model for triggering AI remediation."""

    alert_id: Optional[str] = None
    incident_id: Optional[UUID] = None

    @root_validator
    def validate_entity(cls, values):
        alert_id = values.get("alert_id")
        incident_id = values.get("incident_id")
        if not alert_id and not incident_id:
            raise ValueError("Either alert_id or incident_id must be provided")
        if alert_id and incident_id:
            raise ValueError("Only one of alert_id or incident_id should be provided")
        return values


class AIRemediationResponse(BaseModel):
    """Response model for AI remediation trigger."""

    job_id: str
    status: str  # "enqueued", "processing", "completed", "failed"
    message: str
    pr_url: Optional[str] = None
    rca_summary: Optional[str] = None
