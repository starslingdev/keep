"""
Sentry evidence fetcher for extracting stacktraces and error context.
Uses the tenant's configured Sentry provider credentials.
"""

import logging
import re
from typing import Optional

import requests

from keep.api.models.alert import AlertDto

logger = logging.getLogger(__name__)


class SentryEvidenceFetcher:
    """Fetches evidence from Sentry for RCA using tenant's provider credentials."""
    
    SENTRY_API_BASE = "https://sentry.io/api/0"
    
    def __init__(self, tenant_id: str):
        """
        Initialize the fetcher with tenant's Sentry credentials.
        
        Args:
            tenant_id: The tenant ID to look up Sentry provider for
        """
        self.tenant_id = tenant_id
        self.auth_token: Optional[str] = None
        self.org_slug: Optional[str] = None
        
        # Try to get Sentry credentials from tenant's installed providers
        self._load_tenant_sentry_credentials()
    
    def _load_tenant_sentry_credentials(self) -> None:
        """Load Sentry credentials from the tenant's installed providers."""
        try:
            from keep.api.core.db import get_installed_providers
            from keep.secretmanager.secretmanagerfactory import SecretManagerFactory
            
            providers = get_installed_providers(self.tenant_id)
            
            # Find Sentry provider
            sentry_provider = None
            for provider in providers:
                if provider.type == "sentry":
                    sentry_provider = provider
                    break
            
            if not sentry_provider:
                logger.debug(
                    "No Sentry provider configured for tenant",
                    extra={"tenant_id": self.tenant_id},
                )
                return
            
            # Get the provider's authentication config
            # The configuration is stored encrypted, need to decrypt it
            secret_manager = SecretManagerFactory.get_secret_manager()
            
            # Provider config contains the authentication details
            config = sentry_provider.configuration
            if config and isinstance(config, dict):
                auth_config = config.get("authentication", {})
                
                # Try to get the API key - it might be stored directly or as a secret reference
                api_key = auth_config.get("api_key") or auth_config.get("api_token")
                
                if api_key:
                    # Check if it's a secret reference (starts with secret://)
                    if isinstance(api_key, str) and api_key.startswith("secret://"):
                        try:
                            api_key = secret_manager.read_secret(
                                api_key.replace("secret://", ""),
                                is_json=False,
                            )
                        except Exception as e:
                            logger.warning(f"Failed to read Sentry API key from secret manager: {e}")
                            api_key = None
                    
                    self.auth_token = api_key
                    self.org_slug = auth_config.get("organization_slug") or auth_config.get("org_slug")
                    
                    logger.info(
                        "Loaded Sentry credentials from tenant provider",
                        extra={
                            "tenant_id": self.tenant_id,
                            "provider_id": sentry_provider.id,
                            "has_org": bool(self.org_slug),
                        },
                    )
            
        except Exception as e:
            logger.warning(
                f"Failed to load Sentry credentials for tenant: {e}",
                extra={"tenant_id": self.tenant_id},
            )
    
    def fetch_issue_evidence(self, alert: AlertDto) -> Optional[dict]:
        """
        Fetch Sentry issue evidence from alert.
        
        Looks for sentry_issue_id in alert payload or enrichments.
        
        Returns:
            dict with keys: issue_id, issue_url, exception_type, 
                          stacktrace_top_frame, message, or None if not available
        """
        if not self.auth_token:
            logger.debug(
                "No Sentry credentials available for tenant",
                extra={"tenant_id": self.tenant_id},
            )
            return None
        
        # Try to extract Sentry issue ID from alert
        sentry_issue_id = self._extract_sentry_issue_id(alert)
        
        if not sentry_issue_id:
            logger.debug("No Sentry issue ID found in alert")
            return None
        
        logger.info(
            "Fetching Sentry evidence",
            extra={"sentry_issue_id": sentry_issue_id, "tenant_id": self.tenant_id},
        )
        
        try:
            issue_data = self._fetch_issue_details(sentry_issue_id)
            
            if not issue_data:
                return None
            
            # Extract relevant evidence
            evidence = self._extract_evidence_from_issue(issue_data, sentry_issue_id)
            
            logger.info(
                "Sentry evidence fetched successfully",
                extra={"sentry_issue_id": sentry_issue_id},
            )
            
            return evidence
            
        except Exception as e:
            logger.exception(
                "Failed to fetch Sentry evidence",
                extra={"sentry_issue_id": sentry_issue_id, "error": str(e)},
            )
            return None
    
    def _extract_sentry_issue_id(self, alert: AlertDto) -> Optional[str]:
        """Extract Sentry issue ID from alert."""
        # Check various common field names
        field_names = [
            "sentry_issue_id",
            "sentry_id", 
            "sentryIssueId",
            "sentryId",
            "issue_id",
            "issueId",
        ]
        
        # Check alert attributes
        for field_name in field_names:
            if hasattr(alert, field_name):
                value = getattr(alert, field_name)
                if value:
                    return str(value)
        
        # Check alert fingerprint - Sentry alerts often use issue ID as fingerprint
        if alert.fingerprint and alert.fingerprint.isdigit():
            # Could be a Sentry issue ID
            return alert.fingerprint
        
        # Check for Sentry source
        if alert.source and "sentry" in [s.lower() for s in alert.source]:
            # For Sentry alerts, the fingerprint is often the issue ID
            if alert.fingerprint:
                return alert.fingerprint
        
        # Check for Sentry URLs in description, message, or url
        for field in ["description", "message", "url"]:
            value = getattr(alert, field, "") or ""
            if "sentry.io" in value:
                # Try to extract issue ID from URL
                # Format: https://sentry.io/organizations/org-slug/issues/1234567890/
                match = re.search(r"sentry\.io/.*/issues/(\d+)", value)
                if match:
                    return match.group(1)
        
        return None
    
    def _fetch_issue_details(self, issue_id: str) -> Optional[dict]:
        """Fetch issue details from Sentry API."""
        if not self.auth_token:
            return None
        
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }
        
        # Try to fetch issue directly
        url = f"{self.SENTRY_API_BASE}/issues/{issue_id}/"
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            issue_data = response.json()
            
            logger.debug(
                "Fetched Sentry issue details",
                extra={"issue_id": issue_id},
            )
            
            return issue_data
            
        except requests.HTTPError as e:
            logger.warning(
                f"Failed to fetch Sentry issue {issue_id}: {e.response.status_code}",
            )
            return None
        except Exception as e:
            logger.warning(f"Error fetching Sentry issue: {e}")
            return None
    
    def _fetch_latest_event(self, issue_id: str) -> Optional[dict]:
        """Fetch the latest event for an issue to get stacktrace."""
        if not self.auth_token:
            return None
        
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }
        
        # Get latest event for the issue
        url = f"{self.SENTRY_API_BASE}/issues/{issue_id}/events/latest/"
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            event_data = response.json()
            
            logger.debug(
                "Fetched Sentry latest event",
                extra={"issue_id": issue_id},
            )
            
            return event_data
            
        except Exception as e:
            logger.warning(f"Failed to fetch latest event for issue {issue_id}: {e}")
            return None
    
    def _extract_evidence_from_issue(
        self,
        issue_data: dict,
        issue_id: str,
    ) -> dict:
        """Extract relevant evidence from Sentry issue data."""
        evidence = {
            "issue_id": issue_id,
            "issue_url": issue_data.get("permalink", f"https://sentry.io/issues/{issue_id}/"),
        }
        
        # Extract exception type
        if "metadata" in issue_data:
            metadata = issue_data["metadata"]
            if "type" in metadata:
                evidence["exception_type"] = metadata["type"]
            if "value" in metadata:
                evidence["message"] = metadata["value"]
        
        # Extract culprit (code location)
        if "culprit" in issue_data:
            evidence["culprit"] = issue_data["culprit"]
        
        # Extract project info
        if "project" in issue_data:
            project = issue_data["project"]
            evidence["project_name"] = project.get("name") or project.get("slug")
        
        # Try to get stacktrace from latest event
        try:
            event_data = self._fetch_latest_event(issue_id)
            if event_data:
                stacktrace = self._extract_stacktrace_top_frame(event_data)
                if stacktrace:
                    evidence["stacktrace_top_frame"] = stacktrace
                
                # Also get full stacktrace for context
                full_stacktrace = self._extract_full_stacktrace(event_data)
                if full_stacktrace:
                    evidence["full_stacktrace"] = full_stacktrace
        except Exception as e:
            logger.debug(f"Could not extract stacktrace: {e}")
        
        return evidence
    
    def _extract_stacktrace_top_frame(self, event_data: dict) -> Optional[str]:
        """Extract the top frame from stacktrace."""
        try:
            # Navigate to exception stacktrace
            if "exception" in event_data:
                exceptions = event_data["exception"].get("values", [])
                if exceptions:
                    # Get the last exception (most recent)
                    exception = exceptions[-1]
                    stacktrace = exception.get("stacktrace", {})
                    frames = stacktrace.get("frames", [])
                    
                    if frames:
                        # Get the last frame (top of stack)
                        top_frame = frames[-1]
                        
                        filename = top_frame.get("filename", "unknown")
                        function = top_frame.get("function", "unknown")
                        lineno = top_frame.get("lineno", "?")
                        
                        return f"{filename}:{lineno} in {function}"
            
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting stacktrace: {e}")
            return None
    
    def _extract_full_stacktrace(self, event_data: dict) -> Optional[str]:
        """Extract the full stacktrace as formatted text."""
        try:
            if "exception" not in event_data:
                return None
            
            exceptions = event_data["exception"].get("values", [])
            if not exceptions:
                return None
            
            lines = []
            for exc in exceptions:
                exc_type = exc.get("type", "Exception")
                exc_value = exc.get("value", "")
                lines.append(f"{exc_type}: {exc_value}")
                
                stacktrace = exc.get("stacktrace", {})
                frames = stacktrace.get("frames", [])
                
                # Show last 5 frames
                for frame in frames[-5:]:
                    filename = frame.get("filename", "unknown")
                    function = frame.get("function", "unknown")
                    lineno = frame.get("lineno", "?")
                    context_line = frame.get("context_line", "").strip()
                    
                    lines.append(f"  at {function} ({filename}:{lineno})")
                    if context_line:
                        lines.append(f"    > {context_line}")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.debug(f"Error extracting full stacktrace: {e}")
            return None
