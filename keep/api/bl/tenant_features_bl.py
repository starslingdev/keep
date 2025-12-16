"""
Tenant features and entitlements business logic.
Manages which features are enabled for each tenant.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from keep.api.core.db import get_tenant
from keep.api.consts import KEEP_AI_REMEDIATION_ENABLED

logger = logging.getLogger(__name__)


class TenantFeaturesBl:
    """Manages tenant feature access and entitlements."""
    
    def __init__(self, tenant_id: str, session: Session):
        self.tenant_id = tenant_id
        self.session = session
    
    def has_feature_access(self, feature_name: str) -> bool:
        """
        Check if tenant has access to a specific feature.
        
        Args:
            feature_name: Feature identifier (e.g., "ai_remediation")
        
        Returns:
            True if tenant has access, False otherwise
        """
        # Global feature flag check first
        if feature_name == "ai_remediation" and not KEEP_AI_REMEDIATION_ENABLED:
            logger.debug(
                "AI remediation globally disabled",
                extra={"tenant_id": self.tenant_id},
            )
            return False
        
        # Get tenant configuration
        tenant = get_tenant(self.tenant_id, self.session)
        
        if not tenant:
            logger.warning(
                "Tenant not found",
                extra={"tenant_id": self.tenant_id},
            )
            return False
        
        # Check tenant-specific configuration
        if tenant.configuration:
            tenant_config = tenant.configuration
            
            # Check for feature-specific flag
            feature_key = f"{feature_name}_enabled"
            if feature_key in tenant_config:
                is_enabled = tenant_config[feature_key]
                logger.debug(
                    f"Feature {feature_name} check",
                    extra={
                        "tenant_id": self.tenant_id,
                        "feature": feature_name,
                        "enabled": is_enabled,
                    },
                )
                return is_enabled
        
        # Default: if global flag is on, allow access
        # This means new tenants get the feature by default
        logger.debug(
            f"Feature {feature_name} using default (global flag)",
            extra={"tenant_id": self.tenant_id},
        )
        return KEEP_AI_REMEDIATION_ENABLED
    
    def get_feature_quota(self, feature_name: str) -> Optional[int]:
        """
        Get usage quota for a feature.
        
        Args:
            feature_name: Feature identifier
        
        Returns:
            Quota limit or None for unlimited
        """
        tenant = get_tenant(self.tenant_id, self.session)
        
        if not tenant or not tenant.configuration:
            return None
        
        # Check for quota in tenant config
        quota_key = f"{feature_name}_quota"
        return tenant.configuration.get(quota_key)
    
    def get_feature_usage(self, feature_name: str, period: str = "monthly") -> int:
        """
        Get current usage count for a feature.
        
        Args:
            feature_name: Feature identifier
            period: "monthly", "daily", or "total"
        
        Returns:
            Usage count
        """
        # TODO: Implement usage tracking
        # For AI remediation, count enrichments with ai_remediation_status
        # in the current period
        
        return 0
    
    def check_quota_available(self, feature_name: str) -> bool:
        """
        Check if tenant has quota remaining for a feature.
        
        Returns:
            True if quota available or unlimited, False if quota exceeded
        """
        quota = self.get_feature_quota(feature_name)
        
        # No quota configured = unlimited
        if quota is None:
            return True
        
        usage = self.get_feature_usage(feature_name)
        
        logger.debug(
            "Quota check",
            extra={
                "tenant_id": self.tenant_id,
                "feature": feature_name,
                "usage": usage,
                "quota": quota,
            },
        )
        
        return usage < quota
    
    def increment_usage(self, feature_name: str):
        """
        Increment usage counter for a feature.
        
        Args:
            feature_name: Feature identifier
        """
        # TODO: Implement usage tracking
        # Store usage events in a separate table for analytics
        logger.info(
            "Feature used",
            extra={
                "tenant_id": self.tenant_id,
                "feature": feature_name,
            },
        )

