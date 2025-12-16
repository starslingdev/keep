import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from keep.api.consts import KEEP_AI_REMEDIATION_ENABLED, REDIS, KEEP_ARQ_QUEUE_BASIC
from keep.api.core.db import (
    get_alerts_by_fingerprint,
    get_alerts_count,
    get_enrichment,
    get_first_alert_datetime,
    get_incident_by_id,
    get_incidents_count,
    get_or_create_external_ai_settings,
    get_session,
    update_extrnal_ai_settings,
)
from keep.api.models.ai_external import ExternalAIConfigAndMetadataDto
from keep.api.models.ai_remediation import (
    AIRemediationRequest,
    AIRemediationResponse,
)
from keep.identitymanager.authenticatedentity import AuthenticatedEntity
from keep.identitymanager.identitymanagerfactory import IdentityManagerFactory

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get(
    "/stats",
    description="Get stats for the AI Landing Page",
    include_in_schema=False,
)
def get_stats(
    authenticated_entity: AuthenticatedEntity = Depends(
        IdentityManagerFactory.get_auth_verifier(["read:alert"])
    ),
):
    tenant_id = authenticated_entity.tenant_id
    external_ai_settings = get_or_create_external_ai_settings(tenant_id)

    for setting in external_ai_settings:
        setting.algorithm.remind_about_the_client(tenant_id)

    return {
        "alerts_count": get_alerts_count(tenant_id),
        "first_alert_datetime": get_first_alert_datetime(tenant_id),
        "incidents_count": get_incidents_count(tenant_id),
        "algorithm_configs": external_ai_settings,
    }


@router.put(
    "/{algorithm_id}/settings",
    description="Update settings for an external AI",
    include_in_schema=False,
)
def update_settings(
    algorithm_id: str,
    body: ExternalAIConfigAndMetadataDto,
    authenticated_entity: AuthenticatedEntity = Depends(
        IdentityManagerFactory.get_auth_verifier(["write:alert"])
    ),
):
    tenant_id = authenticated_entity.tenant_id
    return update_extrnal_ai_settings(tenant_id, body)


@router.post(
    "/remediate",
    description="Trigger AI-powered Root Cause Analysis and PR creation for an alert or incident",
    status_code=202,
    response_model=AIRemediationResponse,
)
async def trigger_ai_remediation(
    body: AIRemediationRequest,
    bg_tasks: BackgroundTasks,
    authenticated_entity: AuthenticatedEntity = Depends(
        IdentityManagerFactory.get_auth_verifier(["write:alert"])
    ),
    session: Session = Depends(get_session),
):
    """
    Trigger AI remediation for an alert or incident.
    
    This endpoint:
    1. Validates the feature flag is enabled
    2. Validates the alert/incident exists
    3. Enqueues an async background job for analysis
    4. Returns immediately with a job ID
    
    The background job will:
    - Fetch alert/incident context
    - Resolve the target GitHub repository
    - Fetch Sentry evidence (if applicable)
    - Generate a Root Cause Analysis report
    - Create a draft GitHub PR with the RCA
    - Enrich the alert/incident with results
    """
    tenant_id = authenticated_entity.tenant_id
    user_email = authenticated_entity.email
    
    logger.info(
        "AI remediation triggered",
        extra={
            "tenant_id": tenant_id,
            "alert_id": body.alert_id,
            "incident_id": body.incident_id,
            "user": user_email,
        },
    )
    
    # Validate feature access for tenant
    from keep.api.bl.tenant_features_bl import TenantFeaturesBl
    
    features_bl = TenantFeaturesBl(tenant_id=tenant_id, session=session)
    
    if not features_bl.has_feature_access("ai_remediation"):
        logger.warning(
            "AI remediation feature not available for tenant",
            extra={"tenant_id": tenant_id},
        )
        raise HTTPException(
            status_code=403,
            detail="AI remediation feature is not available for your account. Please contact support to enable it.",
        )
    
    # Check quota (if configured)
    if not features_bl.check_quota_available("ai_remediation"):
        logger.warning(
            "AI remediation quota exceeded",
            extra={"tenant_id": tenant_id},
        )
        raise HTTPException(
            status_code=429,
            detail="Monthly AI remediation quota exceeded. Upgrade your plan for more remediations.",
        )
    
    # Validate entity exists and determine type
    entity_type = None
    entity_id = None
    fingerprint = None
    
    if body.alert_id:
        # Check if alert exists
        alerts = get_alerts_by_fingerprint(
            tenant_id=tenant_id,
            fingerprint=body.alert_id,
            limit=1,
        )
        if not alerts:
            logger.warning(
                "Alert not found",
                extra={"tenant_id": tenant_id, "alert_id": body.alert_id},
            )
            raise HTTPException(
                status_code=404,
                detail=f"Alert with fingerprint {body.alert_id} not found",
            )
        entity_type = "alert"
        entity_id = body.alert_id
        fingerprint = body.alert_id
        
    elif body.incident_id:
        # Check if incident exists
        incident = get_incident_by_id(tenant_id=tenant_id, incident_id=body.incident_id)
        if not incident:
            logger.warning(
                "Incident not found",
                extra={"tenant_id": tenant_id, "incident_id": body.incident_id},
            )
            raise HTTPException(
                status_code=404,
                detail=f"Incident {body.incident_id} not found",
            )
        entity_type = "incident"
        entity_id = str(body.incident_id)
        fingerprint = str(body.incident_id)
    
    # Check if remediation already in progress
    existing_enrichment = get_enrichment(tenant_id=tenant_id, fingerprint=fingerprint)
    if existing_enrichment and existing_enrichment.enrichments.get("ai_remediation_status") == "pending":
        logger.info(
            "AI remediation already in progress",
            extra={"tenant_id": tenant_id, "entity_id": entity_id},
        )
        return AIRemediationResponse(
            job_id=existing_enrichment.enrichments.get("ai_job_id", "existing"),
            status="processing",
            message="AI remediation is already in progress for this entity",
        )
    
    # Generate job ID
    job_id = str(uuid4())
    
    # Enqueue async job
    if REDIS:
        from keep.api.arq_pool import get_pool
        from arq.connections import ArqRedis
        
        logger.info(
            "Enqueueing AI remediation job to ARQ",
            extra={
                "job_id": job_id,
                "tenant_id": tenant_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
        )
        
        try:
            redis: ArqRedis = await get_pool()
            arq_job = await redis.enqueue_job(
                "async_ai_remediation",
                tenant_id,
                entity_type,
                entity_id,
                fingerprint,
                user_email,
                job_id,
                _queue_name=KEEP_ARQ_QUEUE_BASIC,
            )
            logger.info(
                "AI remediation job enqueued",
                extra={
                    "job_id": job_id,
                    "arq_job_id": arq_job.job_id,
                    "queue": KEEP_ARQ_QUEUE_BASIC,
                },
            )
        except Exception as e:
            logger.exception(
                "Failed to enqueue AI remediation job",
                extra={"job_id": job_id, "error": str(e)},
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to enqueue remediation job: {str(e)}",
            )
    else:
        # Use FastAPI background tasks as fallback
        from keep.api.tasks.ai_remediation_task import process_ai_remediation
        
        logger.info(
            "Running AI remediation in background task (non-Redis mode)",
            extra={"job_id": job_id, "tenant_id": tenant_id},
        )
        
        bg_tasks.add_task(
            process_ai_remediation,
            {},
            tenant_id,
            entity_type,
            entity_id,
            fingerprint,
            user_email,
            job_id,
        )
    
    return AIRemediationResponse(
        job_id=job_id,
        status="enqueued",
        message=f"AI remediation job enqueued successfully for {entity_type} {entity_id}",
    )
