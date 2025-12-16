"""
Sentry evidence fetcher for extracting stacktraces and error context.
"""

import logging
from typing import Optional

import requests

from keep.api.consts import SENTRY_AUTH_TOKEN, SENTRY_DEFAULT_ORG
from keep.api.models.alert import AlertDto

logger = logging.getLogger(__name__)


class SentryEvidenceFetcher:
    """Fetches evidence from Sentry for RCA."""
    
    SENTRY_API_BASE = "https://sentry.io/api/0"
    
    def __init__(self):
        self.auth_token = SENTRY_AUTH_TOKEN
        self.default_org = SENTRY_DEFAULT_ORG
    
    def fetch_issue_evidence(self, alert: AlertDto) -> Optional[dict]:
        """
        Fetch Sentry issue evidence from alert.
        
        Looks for sentry_issue_id in alert payload or enrichments.
        
        Returns:
            dict with keys: issue_id, issue_url, exception_type, 
                          stacktrace_top_frame, message, or None if not available
        """
        if not self.auth_token:
            logger.debug("Sentry auth token not configured, skipping evidence fetch")
            return None
        
        # Try to extract Sentry issue ID from alert
        sentry_issue_id = self._extract_sentry_issue_id(alert)
        
        if not sentry_issue_id:
            logger.debug("No Sentry issue ID found in alert")
            return None
        
        logger.info(
            "Fetching Sentry evidence",
            extra={"sentry_issue_id": sentry_issue_id},
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
        
        # Check alert event dict (raw payload)
        if hasattr(alert, "event") and isinstance(alert.event, dict):
            for field_name in field_names:
                if field_name in alert.event:
                    return str(alert.event[field_name])
        
        # Check for Sentry URLs in description or message
        description = getattr(alert, "description", "")
        if "sentry.io" in description:
            # Try to extract issue ID from URL
            # Format: https://sentry.io/organizations/org-slug/issues/1234567890/
            import re
            match = re.search(r"sentry\.io/.*/issues/(\d+)", description)
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
            logger.exception(f"Error fetching Sentry issue: {e}")
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
        
        # Try to get stacktrace from latest event
        try:
            event_data = self._fetch_latest_event(issue_id)
            if event_data:
                stacktrace = self._extract_stacktrace_top_frame(event_data)
                if stacktrace:
                    evidence["stacktrace_top_frame"] = stacktrace
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

