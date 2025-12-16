"""
Business logic for AI remediation: repository resolution, RCA generation, and PR creation.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from keep.api.bl.rca_generator import RCAGenerator
from keep.api.bl.github_pr_creator import GitHubPRCreator
from keep.api.bl.sentry_evidence_fetcher import SentryEvidenceFetcher
from keep.api.consts import (
    AI_REMEDIATION_SERVICE_MAPPING,
    GITHUB_APP_ID,
    GITHUB_PRIVATE_KEY,
    GITHUB_PRIVATE_KEY_PATH,
    KEEP_AI_CREATE_GITHUB_PR,
)
from keep.api.core.db import (
    _enrich_entity,
    get_alerts_by_fingerprint,
    get_incident,
)
from keep.api.models.action_type import ActionType
from keep.api.models.ai_remediation import AIRemediationEnrichment, RCAReport
from keep.api.models.alert import AlertDto
from keep.api.models.incident import IncidentDto
from keep.api.utils.enrichment_helpers import convert_db_alerts_to_dto_alerts

logger = logging.getLogger(__name__)


class AIRemediationBl:
    """Business logic for AI remediation operations."""
    
    def __init__(self, tenant_id: str, session: Session):
        self.tenant_id = tenant_id
        self.session = session
        self.rca_generator = RCAGenerator()
        self.sentry_fetcher = SentryEvidenceFetcher()
        
        # Initialize GitHub PR creator if configured (optional feature)
        self.github_pr_creator = None
        if KEEP_AI_CREATE_GITHUB_PR and GITHUB_APP_ID and (GITHUB_PRIVATE_KEY or GITHUB_PRIVATE_KEY_PATH):
            try:
                self.github_pr_creator = GitHubPRCreator(
                    app_id=GITHUB_APP_ID,
                    private_key=GITHUB_PRIVATE_KEY,
                    private_key_path=GITHUB_PRIVATE_KEY_PATH,
                )
                logger.info("GitHub PR creator initialized")
            except Exception as e:
                logger.warning(
                    "Failed to initialize GitHub PR creator (optional feature disabled)",
                    extra={"error": str(e)},
                )
    
    def mark_remediation_pending(
        self,
        fingerprint: str,
        job_id: str,
        started_at: datetime,
        user_email: str,
    ):
        """Mark remediation as pending in enrichment."""
        enrichment_data = {
            "ai_remediation_status": "pending",
            "ai_remediation_started_at": started_at.isoformat(),
            "ai_job_id": job_id,
        }
        
        _enrich_entity(
            session=self.session,
            tenant_id=self.tenant_id,
            fingerprint=fingerprint,
            enrichments=enrichment_data,
            action_type=ActionType.AI_REMEDIATION_STARTED,
            action_callee=user_email,
            action_description="AI remediation started",
        )
        
        logger.info(
            "Marked remediation as pending",
            extra={"fingerprint": fingerprint, "job_id": job_id},
        )
    
    def fetch_entity_context(
        self,
        entity_type: str,
        entity_id: str,
    ) -> dict:
        """
        Fetch alert or incident context from database.
        
        Returns:
            dict with keys: type, id, alert (AlertDto or list), incident (IncidentDto), enrichments
        """
        logger.info(
            "Fetching entity context",
            extra={"entity_type": entity_type, "entity_id": entity_id},
        )
        
        if entity_type == "alert":
            # Fetch alert by fingerprint
            db_alerts = get_alerts_by_fingerprint(
                tenant_id=self.tenant_id,
                fingerprint=entity_id,
                limit=1,
            )
            
            if not db_alerts:
                raise ValueError(f"Alert {entity_id} not found")
            
            alerts_dto = convert_db_alerts_to_dto_alerts(
                db_alerts,
                with_incidents=True,
                session=self.session,
            )
            
            alert = alerts_dto[0]
            enrichments = db_alerts[0].alert_enrichment.enrichments if db_alerts[0].alert_enrichment else {}
            
            return {
                "type": "alert",
                "id": entity_id,
                "alert": alert,
                "enrichments": enrichments,
            }
            
        elif entity_type == "incident":
            # Fetch incident
            incident_dto = get_incident(
                tenant_id=self.tenant_id,
                incident_id=entity_id,
            )
            
            if not incident_dto:
                raise ValueError(f"Incident {entity_id} not found")
            
            # Fetch associated alerts
            # TODO: Implement fetching incident alerts
            
            return {
                "type": "incident",
                "id": entity_id,
                "incident": incident_dto,
                "enrichments": {},  # TODO: Get incident enrichments
            }
        
        else:
            raise ValueError(f"Unknown entity type: {entity_type}")
    
    def resolve_repository(self, entity_context: dict) -> Optional[str]:
        """
        Resolve target GitHub repository (optional - only needed for PR creation).
        
        Priority:
        1. Check alert/incident tags for repo=owner/name or github_repo=owner/name
        2. Check service mapping configuration
        3. Return None (not an error if PR creation is disabled)
        
        Returns:
            Repository in format "owner/name" or None
        """
        # Skip repo resolution if PR creation is disabled
        if not KEEP_AI_CREATE_GITHUB_PR:
            logger.debug("GitHub PR creation disabled, skipping repo resolution")
            return None
        
        logger.info("Resolving repository", extra={"entity_type": entity_context["type"]})
        
        # Priority 1: Check tags
        if entity_context["type"] == "alert":
            alert: AlertDto = entity_context["alert"]
            
            # Check for repo tag
            if hasattr(alert, "repo") and alert.repo:
                logger.info(
                    "Repository found in alert.repo field",
                    extra={"repo": alert.repo},
                )
                return alert.repo
            
            if hasattr(alert, "github_repo") and alert.github_repo:
                logger.info(
                    "Repository found in alert.github_repo field",
                    extra={"repo": alert.github_repo},
                )
                return alert.github_repo
            
            # Check enrichments
            enrichments = entity_context.get("enrichments", {})
            if "repo" in enrichments:
                logger.info(
                    "Repository found in enrichments",
                    extra={"repo": enrichments["repo"]},
                )
                return enrichments["repo"]
            
            if "github_repo" in enrichments:
                logger.info(
                    "Repository found in enrichments",
                    extra={"repo": enrichments["github_repo"]},
                )
                return enrichments["github_repo"]
            
            # Priority 2: Check service mapping
            service = getattr(alert, "service", None)
            if service:
                repo = self._resolve_from_service_mapping(service)
                if repo:
                    logger.info(
                        "Repository resolved from service mapping",
                        extra={"service": service, "repo": repo},
                    )
                    return repo
        
        elif entity_context["type"] == "incident":
            incident: IncidentDto = entity_context["incident"]
            
            # Check incident enrichments
            # TODO: Implement incident enrichment checks
            
            # Check affected services
            if incident.affected_services:
                for service in incident.affected_services:
                    repo = self._resolve_from_service_mapping(service)
                    if repo:
                        logger.info(
                            "Repository resolved from incident service mapping",
                            extra={"service": service, "repo": repo},
                        )
                        return repo
        
        logger.warning(
            "Could not resolve repository",
            extra={"entity_type": entity_context["type"]},
        )
        return None
    
    def _resolve_from_service_mapping(self, service: str) -> Optional[str]:
        """Resolve repository from service mapping configuration."""
        try:
            mapping = json.loads(AI_REMEDIATION_SERVICE_MAPPING)
            return mapping.get(service)
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse service mapping JSON",
                extra={"mapping": AI_REMEDIATION_SERVICE_MAPPING},
            )
            return None
    
    def fetch_sentry_evidence(self, entity_context: dict) -> Optional[dict]:
        """
        Fetch Sentry evidence if available.
        
        Returns:
            dict with Sentry evidence or None if not available
        """
        if entity_context["type"] == "alert":
            alert: AlertDto = entity_context["alert"]
            return self.sentry_fetcher.fetch_issue_evidence(alert)
        
        return None
    
    def generate_rca_report(
        self,
        entity_context: dict,
        sentry_evidence: Optional[dict],
        repo: str,
    ) -> RCAReport:
        """Generate Root Cause Analysis report."""
        logger.info("Generating RCA report", extra={"repo": repo})
        
        if entity_context["type"] == "alert":
            alert: AlertDto = entity_context["alert"]
            return self.rca_generator.generate_rca_report(
                alert=alert,
                sentry_evidence=sentry_evidence,
                repo=repo,
            )
        elif entity_context["type"] == "incident":
            # TODO: Implement incident RCA generation
            incident: IncidentDto = entity_context["incident"]
            # For now, create a basic report from incident data
            return self.rca_generator.generate_incident_rca_report(
                incident=incident,
                sentry_evidence=sentry_evidence,
                repo=repo,
            )
        
        raise ValueError(f"Unknown entity type: {entity_context['type']}")
    
    def create_github_pr(
        self,
        repo: str,
        entity_id: str,
        entity_type: str,
        rca_report: RCAReport,
        entity_context: dict,
    ) -> Optional[str]:
        """
        Create GitHub PR with RCA and attempted fix (optional feature).
        
        Returns:
            PR URL or None if PR creation is disabled
        """
        if not KEEP_AI_CREATE_GITHUB_PR:
            logger.info("GitHub PR creation is disabled, skipping")
            return None
        
        if not self.github_pr_creator:
            logger.warning(
                "GitHub PR creator not initialized (missing credentials), skipping PR creation"
            )
            return None
        
        if not repo:
            logger.warning("No repository resolved, cannot create PR")
            return None
        
        logger.info(
            "Creating GitHub PR",
            extra={"repo": repo, "entity_id": entity_id},
        )
        
        # Get Keep base URL for linking back
        import os
        keep_base_url = os.environ.get("KEEP_FRONTEND_URL", "")
        entity_link = f"{keep_base_url}/{entity_type}s/{entity_id}" if keep_base_url else f"/{entity_type}s/{entity_id}"
        
        try:
            pr_url = self.github_pr_creator.create_remediation_pr(
                repo=repo,
                entity_id=entity_id,
                entity_type=entity_type,
                rca_report=rca_report,
                keep_entity_link=entity_link,
            )
            
            logger.info(
                "GitHub PR created successfully",
                extra={"repo": repo, "pr_url": pr_url},
            )
            
            return pr_url
        except Exception as e:
            logger.exception(
                "Failed to create GitHub PR, continuing without it",
                extra={"error": str(e)},
            )
            return None
    
    def update_enrichment_with_results(
        self,
        fingerprint: str,
        enrichment_data: AIRemediationEnrichment,
        user_email: str,
    ):
        """Update enrichment with remediation results."""
        enrichments = enrichment_data.dict(exclude_none=True)
        
        # Convert datetime objects to ISO strings
        for key, value in enrichments.items():
            if isinstance(value, datetime):
                enrichments[key] = value.isoformat()
        
        action_type = (
            ActionType.AI_REMEDIATION_COMPLETED
            if enrichment_data.ai_remediation_status == "success"
            else ActionType.AI_REMEDIATION_FAILED
        )
        
        action_description = (
            f"AI remediation completed: {enrichment_data.ai_rca_summary or 'RCA generated'}"
            if enrichment_data.ai_remediation_status == "success"
            else f"AI remediation failed: {enrichment_data.ai_error_message}"
        )
        
        _enrich_entity(
            session=self.session,
            tenant_id=self.tenant_id,
            fingerprint=fingerprint,
            enrichments=enrichments,
            action_type=action_type,
            action_callee=user_email,
            action_description=action_description,
        )
        
        logger.info(
            "Updated enrichment with remediation results",
            extra={
                "fingerprint": fingerprint,
                "status": enrichment_data.ai_remediation_status,
            },
        )

