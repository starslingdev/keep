"""
AI Remediation background task for processing RCA and PR creation.
"""

import asyncio
import logging
from datetime import datetime

from keep.api.bl.ai_remediation_bl import AIRemediationBl
from keep.api.core.db import get_session_sync
from keep.api.models.ai_remediation import AIRemediationEnrichment

logger = logging.getLogger(__name__)


async def async_ai_remediation(
    ctx,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    fingerprint: str,
    user_email: str,
    job_id: str,
):
    """
    Async ARQ task for AI remediation.
    
    Args:
        ctx: ARQ context
        tenant_id: Tenant ID
        entity_type: "alert" or "incident"
        entity_id: Entity ID (alert fingerprint or incident UUID)
        fingerprint: Fingerprint for enrichment (same as entity_id for alerts, incident UUID for incidents)
        user_email: User who triggered the remediation
        job_id: Unique job ID
    """
    logger.info(
        "AI remediation task started",
        extra={
            "job_id": job_id,
            "tenant_id": tenant_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
        },
    )
    
    # Run the sync version in executor
    loop = asyncio.get_running_loop()
    pool = ctx.get("pool")
    
    try:
        await loop.run_in_executor(
            pool,
            process_ai_remediation,
            ctx,
            tenant_id,
            entity_type,
            entity_id,
            fingerprint,
            user_email,
            job_id,
        )
        logger.info(
            "AI remediation task completed",
            extra={"job_id": job_id, "tenant_id": tenant_id},
        )
    except Exception as e:
        logger.exception(
            "AI remediation task failed",
            extra={"job_id": job_id, "tenant_id": tenant_id, "error": str(e)},
        )
        # Update enrichment with error
        _update_enrichment_with_error(tenant_id, fingerprint, str(e), user_email)
        raise


def process_ai_remediation(
    ctx,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    fingerprint: str,
    user_email: str,
    job_id: str,
):
    """
    Synchronous processing function for AI remediation.
    
    This function:
    1. Fetches alert/incident context from DB
    2. Resolves target GitHub repository
    3. Fetches Sentry evidence (if applicable)
    4. Generates RCA report
    5. Creates GitHub PR with RCA and attempted fix
    6. Enriches entity with results
    """
    logger.info(
        "Processing AI remediation",
        extra={
            "job_id": job_id,
            "tenant_id": tenant_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
        },
    )
    
    started_at = datetime.utcnow()
    
    try:
        with get_session_sync() as session:
            # Initialize business logic handler
            remediation_bl = AIRemediationBl(tenant_id=tenant_id, session=session)
            
            # Note: "pending" status is already set by the route before this task starts
            
            # Step 1: Fetch entity context
            logger.info(
                "Fetching entity context",
                extra={"job_id": job_id, "entity_type": entity_type},
            )
            entity_context = remediation_bl.fetch_entity_context(
                entity_type=entity_type,
                entity_id=entity_id,
            )
            
            if not entity_context:
                raise ValueError(f"Could not fetch context for {entity_type} {entity_id}")
            
            # Step 2: Resolve repository (optional - only for PR creation)
            logger.info("Resolving target repository", extra={"job_id": job_id})
            repo = remediation_bl.resolve_repository(entity_context)
            
            if repo:
                logger.info(
                    "Repository resolved",
                    extra={"job_id": job_id, "repo": repo},
                )
            else:
                logger.info(
                    "No repository resolved (PR creation disabled or no repo tags)",
                    extra={"job_id": job_id},
                )
                repo = "N/A"  # Continue without repo for RCA-only mode
            
            # Step 3: Fetch Sentry evidence (optional)
            logger.info("Fetching Sentry evidence", extra={"job_id": job_id})
            sentry_evidence = remediation_bl.fetch_sentry_evidence(entity_context)
            
            if sentry_evidence:
                logger.info(
                    "Sentry evidence fetched",
                    extra={
                        "job_id": job_id,
                        "sentry_issue_id": sentry_evidence.get("issue_id"),
                    },
                )
            else:
                logger.info(
                    "No Sentry evidence found, proceeding without it",
                    extra={"job_id": job_id},
                )
            
            # Step 4: Generate RCA report
            logger.info("Generating RCA report", extra={"job_id": job_id})
            rca_report = remediation_bl.generate_rca_report(
                entity_context=entity_context,
                sentry_evidence=sentry_evidence,
                repo=repo,
            )
            
            logger.info(
                "RCA report generated",
                extra={"job_id": job_id, "summary": rca_report.summary},
            )
            
            # Step 5: Create GitHub PR (optional feature)
            logger.info("Creating GitHub PR (if enabled)", extra={"job_id": job_id})
            pr_url = remediation_bl.create_github_pr(
                repo=repo,
                entity_id=entity_id,
                entity_type=entity_type,
                rca_report=rca_report,
                entity_context=entity_context,
            )
            
            if pr_url:
                logger.info(
                    "GitHub PR created",
                    extra={"job_id": job_id, "pr_url": pr_url},
                )
            else:
                logger.info(
                    "GitHub PR creation skipped (feature disabled or not configured)",
                    extra={"job_id": job_id},
                )
            
            # Step 6: Update enrichment with success
            completed_at = datetime.utcnow()
            enrichment_data = AIRemediationEnrichment(
                ai_remediation_status="success",
                ai_remediation_started_at=started_at,
                ai_remediation_completed_at=completed_at,
                ai_rca_summary=rca_report.summary,
                ai_rca_full_report=rca_report.full_report_markdown,
                ai_pr_url=pr_url,
                ai_repo_resolved=repo,
            )
            
            remediation_bl.update_enrichment_with_results(
                fingerprint=fingerprint,
                enrichment_data=enrichment_data,
                user_email=user_email,
            )
            
            logger.info(
                "AI remediation completed successfully",
                extra={
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "pr_url": pr_url,
                    "duration_seconds": (completed_at - started_at).total_seconds(),
                },
            )
            
    except Exception as e:
        logger.exception(
            "AI remediation failed",
            extra={
                "job_id": job_id,
                "tenant_id": tenant_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "error": str(e),
            },
        )
        _update_enrichment_with_error(tenant_id, fingerprint, str(e), user_email)
        raise


def _update_enrichment_with_error(
    tenant_id: str,
    fingerprint: str,
    error_message: str,
    user_email: str,
):
    """Update enrichment with error status."""
    try:
        with get_session_sync() as session:
            remediation_bl = AIRemediationBl(tenant_id=tenant_id, session=session)
            enrichment_data = AIRemediationEnrichment(
                ai_remediation_status="failed",
                ai_remediation_started_at=datetime.utcnow(),
                ai_remediation_completed_at=datetime.utcnow(),
                ai_error_message=error_message,
            )
            remediation_bl.update_enrichment_with_results(
                fingerprint=fingerprint,
                enrichment_data=enrichment_data,
                user_email=user_email,
            )
    except Exception as e:
        logger.exception(
            "Failed to update enrichment with error",
            extra={"error": str(e)},
        )

