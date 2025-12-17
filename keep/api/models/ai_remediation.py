from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, root_validator


class RCAReport(BaseModel):
    """Root Cause Analysis report structure."""
    
    summary: str
    alert_name: str
    alert_id: str
    severity: str
    service: Optional[str] = None
    error_description: Optional[str] = None
    sentry_issue_id: Optional[str] = None
    stacktrace_top_frame: Optional[str] = None
    hypotheses: List[dict]
    recommended_fix_category: str
    full_report_markdown: str
    generated_at: datetime


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


class AIRemediationEnrichment(BaseModel):
    """Enrichment data stored for AI remediation results."""
    
    ai_remediation_status: str  # "pending", "success", "failed"
    ai_job_id: Optional[str] = None
    ai_remediation_started_at: Optional[datetime] = None
    ai_remediation_completed_at: Optional[datetime] = None
    ai_rca_summary: Optional[str] = None
    ai_rca_full_report: Optional[str] = None
    ai_pr_url: Optional[str] = None
    ai_repo_resolved: Optional[str] = None
    ai_error_message: Optional[str] = None
    ai_recommended_fix_category: Optional[str] = None
    ai_hypotheses: Optional[List[dict]] = None
