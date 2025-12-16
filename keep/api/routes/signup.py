"""
Public signup endpoint for new tenant provisioning.
No authentication required for this endpoint.
"""

import logging
import secrets
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, validator
from sqlalchemy.orm import Session

from keep.api.core.db import (
    create_user,
    get_session,
    user_exists,
)
from keep.api.models.db.tenant import Tenant

router = APIRouter()
logger = logging.getLogger(__name__)


class SignupRequest(BaseModel):
    """Request model for tenant signup."""
    
    email: str
    organization_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    
    @validator("email")
    def validate_email(cls, v):
        if not v or "@" not in v or "." not in v:
            raise ValueError("Invalid email address")
        return v.lower().strip()
    
    @validator("organization_name")
    def validate_org_name(cls, v):
        if len(v) < 2:
            raise ValueError("Organization name must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("Organization name must be less than 100 characters")
        return v


class SignupResponse(BaseModel):
    """Response model for signup."""
    
    tenant_id: str
    organization_name: str
    email: str
    password: str
    login_url: str
    message: str


@router.post(
    "/signup",
    description="Public signup endpoint for new tenant provisioning",
    response_model=SignupResponse,
    include_in_schema=True,
)
def signup_tenant(
    request: SignupRequest,
    session: Session = Depends(get_session),
) -> SignupResponse:
    """
    Create a new tenant and admin user.
    
    This endpoint:
    1. Creates a new tenant with a unique ID
    2. Creates an admin user for the tenant
    3. Enables AI remediation feature by default
    4. Returns credentials for first login
    
    No payment required - this is for early access / beta users.
    """
    logger.info(
        "New tenant signup request",
        extra={
            "email": request.email,
            "organization": request.organization_name,
        },
    )
    
    # Generate tenant ID
    tenant_id = str(uuid4())
    
    try:
        # Check if email already exists across all tenants
        # This prevents duplicate signups
        if _email_exists_in_any_tenant(request.email, session):
            logger.warning(
                "Signup attempted with existing email",
                extra={"email": request.email},
            )
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists. Please sign in or use a different email.",
            )
        
        # Create tenant
        logger.info(
            "Creating new tenant",
            extra={"tenant_id": tenant_id, "org": request.organization_name},
        )
        
        tenant_config = {
            "ai_remediation_enabled": True,  # Enable AI remediation by default
            "created_at": datetime.utcnow().isoformat(),
            "signup_email": request.email,
            "plan": "beta",  # Mark as beta/early access
        }
        
        tenant = Tenant(
            id=tenant_id,
            name=request.organization_name,
            configuration=tenant_config,
        )
        
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        
        logger.info(
            "Tenant created successfully",
            extra={"tenant_id": tenant_id, "org": request.organization_name},
        )
        
        # Generate secure password
        password = secrets.token_urlsafe(16)
        
        # Create admin user
        logger.info(
            "Creating admin user",
            extra={"tenant_id": tenant_id, "email": request.email},
        )
        
        user = create_user(
            tenant_id=tenant_id,
            username=request.email,
            password=password,
            role="admin",
        )
        
        logger.info(
            "Admin user created successfully",
            extra={"tenant_id": tenant_id, "email": request.email},
        )
        
        # TODO: Send welcome email with credentials
        # _send_welcome_email(request.email, tenant_id, password)
        
        # Get Keep frontend URL from environment or use relative path
        import os
        keep_frontend_url = os.environ.get("KEEP_FRONTEND_URL", "")
        login_url = f"{keep_frontend_url}/signin?tenant={tenant_id}" if keep_frontend_url else f"/signin?tenant={tenant_id}"
        
        # Return credentials
        # In production, you'd send these via email instead of returning them
        return SignupResponse(
            tenant_id=tenant_id,
            organization_name=request.organization_name,
            email=request.email,
            password=password,
            login_url=login_url,
            message=(
                "Account created successfully! "
                "Please save your credentials and change your password after first login."
            ),
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
        
    except Exception as e:
        logger.exception(
            "Failed to create tenant",
            extra={
                "email": request.email,
                "error": str(e),
            },
        )
        
        # Rollback is handled by session context
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create account: {str(e)}",
        )


def _email_exists_in_any_tenant(email: str, session: Session) -> bool:
    """Check if email exists in any tenant."""
    from keep.api.models.db.user import User
    from sqlmodel import select
    
    statement = select(User).where(User.username == email)
    user = session.exec(statement).first()
    
    return user is not None


def _send_welcome_email(email: str, tenant_id: str, password: str):
    """
    Send welcome email with credentials.
    
    TODO: Implement email sending using Keep's SMTP provider or SendGrid.
    """
    # Placeholder for email sending
    logger.info(
        "Would send welcome email",
        extra={"email": email, "tenant_id": tenant_id},
    )
    pass

