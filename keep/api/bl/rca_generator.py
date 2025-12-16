"""
Root Cause Analysis generator with deterministic template-based approach.
"""

import logging
from datetime import datetime
from typing import Optional

from keep.api.models.ai_remediation import RCAReport
from keep.api.models.alert import AlertDto
from keep.api.models.incident import IncidentDto

logger = logging.getLogger(__name__)


class RCAGenerator:
    """Generates Root Cause Analysis reports using deterministic templates."""
    
    def generate_rca_report(
        self,
        alert: AlertDto,
        sentry_evidence: Optional[dict],
        repo: str,
    ) -> RCAReport:
        """
        Generate RCA report for an alert.
        
        Args:
            alert: Alert to analyze
            sentry_evidence: Optional Sentry evidence dict
            repo: Target repository (owner/name)
        
        Returns:
            RCAReport with structured analysis
        """
        logger.info(
            "Generating RCA report for alert",
            extra={"alert_name": alert.name, "repo": repo},
        )
        
        # Extract key information
        alert_name = alert.name or "Unnamed Alert"
        severity = getattr(alert, "severity", "unknown")
        service = getattr(alert, "service", "unknown")
        description = getattr(alert, "description", "No description available")
        source = alert.source[0] if alert.source else "unknown"
        
        # Build hypotheses based on available evidence
        hypotheses = self._generate_hypotheses(alert, sentry_evidence)
        
        # Determine recommended fix category
        fix_category = self._determine_fix_category(alert, sentry_evidence)
        
        # Generate summary
        summary = self._generate_summary(alert, sentry_evidence)
        
        # Build full markdown report
        markdown_report = self._build_markdown_report(
            alert_name=alert_name,
            summary=summary,
            description=description,
            severity=severity,
            service=service,
            source=source,
            sentry_evidence=sentry_evidence,
            hypotheses=hypotheses,
            fix_category=fix_category,
            repo=repo,
        )
        
        return RCAReport(
            summary=summary,
            alert_name=alert_name,
            alert_id=alert.fingerprint,
            severity=str(severity),
            service=service,
            error_description=description,
            sentry_issue_id=sentry_evidence.get("issue_id") if sentry_evidence else None,
            stacktrace_top_frame=(
                sentry_evidence.get("stacktrace_top_frame")
                if sentry_evidence
                else None
            ),
            hypotheses=hypotheses,
            recommended_fix_category=fix_category,
            full_report_markdown=markdown_report,
            generated_at=datetime.utcnow(),
        )
    
    def generate_incident_rca_report(
        self,
        incident: IncidentDto,
        sentry_evidence: Optional[dict],
        repo: str,
    ) -> RCAReport:
        """
        Generate RCA report for an incident.
        
        Args:
            incident: Incident to analyze
            sentry_evidence: Optional Sentry evidence dict
            repo: Target repository (owner/name)
        
        Returns:
            RCAReport with structured analysis
        """
        logger.info(
            "Generating RCA report for incident",
            extra={"incident_id": incident.id, "repo": repo},
        )
        
        # Extract key information
        incident_name = incident.user_generated_name or incident.ai_generated_name or f"Incident #{incident.id}"
        severity = incident.severity
        services = ", ".join(incident.affected_services) if incident.affected_services else "unknown"
        description = incident.user_summary or incident.generated_summary or "No description available"
        sources = ", ".join(incident.sources) if incident.sources else "unknown"
        
        # Build hypotheses for incident
        hypotheses = self._generate_incident_hypotheses(incident, sentry_evidence)
        
        # Determine fix category
        fix_category = self._determine_incident_fix_category(incident, sentry_evidence)
        
        # Generate summary
        summary = (
            f"Incident affecting {services} with severity {severity}. "
            f"Analysis suggests {fix_category.lower()} as primary remediation approach."
        )
        
        # Build markdown report
        markdown_report = self._build_incident_markdown_report(
            incident_name=incident_name,
            summary=summary,
            description=description,
            severity=severity,
            services=services,
            sources=sources,
            alerts_count=incident.alerts_count,
            sentry_evidence=sentry_evidence,
            hypotheses=hypotheses,
            fix_category=fix_category,
            repo=repo,
        )
        
        return RCAReport(
            summary=summary,
            alert_name=incident_name,
            alert_id=str(incident.id),
            severity=str(severity),
            service=services,
            error_description=description,
            sentry_issue_id=sentry_evidence.get("issue_id") if sentry_evidence else None,
            stacktrace_top_frame=(
                sentry_evidence.get("stacktrace_top_frame")
                if sentry_evidence
                else None
            ),
            hypotheses=hypotheses,
            recommended_fix_category=fix_category,
            full_report_markdown=markdown_report,
            generated_at=datetime.utcnow(),
        )
    
    def _generate_hypotheses(
        self,
        alert: AlertDto,
        sentry_evidence: Optional[dict],
    ) -> list[dict[str, str]]:
        """Generate ranked hypotheses based on alert and evidence."""
        hypotheses = []
        
        description_lower = getattr(alert, "description", "").lower()
        
        # Hypothesis 1: Check for common error patterns
        if sentry_evidence and sentry_evidence.get("exception_type"):
            exception_type = sentry_evidence["exception_type"]
            if "null" in exception_type.lower() or "none" in exception_type.lower():
                hypotheses.append({
                    "likelihood": "Likely",
                    "description": f"{exception_type} indicating null/undefined access in code",
                })
            elif "timeout" in exception_type.lower():
                hypotheses.append({
                    "likelihood": "Likely",
                    "description": f"{exception_type} indicating timeout or slow response",
                })
            else:
                hypotheses.append({
                    "likelihood": "Likely",
                    "description": f"{exception_type} exception in application code",
                })
        elif "timeout" in description_lower or "timed out" in description_lower:
            hypotheses.append({
                "likelihood": "Likely",
                "description": "Connection timeout or slow external dependency",
            })
        elif "null" in description_lower or "undefined" in description_lower:
            hypotheses.append({
                "likelihood": "Likely",
                "description": "Null pointer or undefined variable access",
            })
        elif "memory" in description_lower or "oom" in description_lower:
            hypotheses.append({
                "likelihood": "Likely",
                "description": "Out of memory or memory leak",
            })
        elif "disk" in description_lower or "space" in description_lower:
            hypotheses.append({
                "likelihood": "Likely",
                "description": "Disk space exhaustion",
            })
        elif "connection" in description_lower or "database" in description_lower:
            hypotheses.append({
                "likelihood": "Likely",
                "description": "Database connection failure or pool exhaustion",
            })
        else:
            hypotheses.append({
                "likelihood": "Possible",
                "description": "Application logic error or unexpected state",
            })
        
        # Hypothesis 2: Infrastructure or dependency issues
        if "5xx" in description_lower or "500" in description_lower:
            hypotheses.append({
                "likelihood": "Possible",
                "description": "Downstream service returning 5xx errors",
            })
        else:
            hypotheses.append({
                "likelihood": "Possible",
                "description": "External dependency failure or degraded performance",
            })
        
        # Hypothesis 3: Less likely but possible
        hypotheses.append({
            "likelihood": "Unlikely",
            "description": "Configuration change or environment mismatch",
        })
        
        return hypotheses
    
    def _generate_incident_hypotheses(
        self,
        incident: IncidentDto,
        sentry_evidence: Optional[dict],
    ) -> list[dict[str, str]]:
        """Generate hypotheses for incident."""
        hypotheses = []
        
        description_lower = (incident.user_summary or incident.generated_summary or "").lower()
        
        # Multi-service incident suggests infrastructure or shared dependency issue
        if incident.affected_services and len(incident.affected_services) > 1:
            hypotheses.append({
                "likelihood": "Likely",
                "description": f"Shared infrastructure or dependency issue affecting {len(incident.affected_services)} services",
            })
        
        # High alert count suggests widespread issue
        if incident.alerts_count > 10:
            hypotheses.append({
                "likelihood": "Likely",
                "description": f"Widespread issue ({incident.alerts_count} alerts) indicating systemic problem",
            })
        
        # Add Sentry-based hypothesis if available
        if sentry_evidence and sentry_evidence.get("exception_type"):
            hypotheses.append({
                "likelihood": "Possible",
                "description": f"Related to {sentry_evidence['exception_type']} in application layer",
            })
        else:
            hypotheses.append({
                "likelihood": "Possible",
                "description": "Application-level issue requiring code fix",
            })
        
        # Configuration or deployment hypothesis
        hypotheses.append({
            "likelihood": "Unlikely",
            "description": "Recent deployment or configuration change",
        })
        
        return hypotheses
    
    def _determine_fix_category(
        self,
        alert: AlertDto,
        sentry_evidence: Optional[dict],
    ) -> str:
        """Determine recommended fix category."""
        description_lower = getattr(alert, "description", "").lower()
        
        if sentry_evidence:
            exception_type = sentry_evidence.get("exception_type", "").lower()
            if "null" in exception_type or "none" in exception_type:
                return "Null check / defensive programming"
            elif "version" in exception_type or "deprecated" in exception_type:
                return "Dependency update"
        
        if "timeout" in description_lower or "slow" in description_lower:
            return "Timeout / retry configuration"
        elif "null" in description_lower or "undefined" in description_lower:
            return "Null check / defensive programming"
        elif "memory" in description_lower:
            return "Memory optimization / leak fix"
        elif "config" in description_lower:
            return "Configuration change"
        elif "version" in description_lower or "deprecated" in description_lower:
            return "Dependency update"
        else:
            return "Code fix / logic update"
    
    def _determine_incident_fix_category(
        self,
        incident: IncidentDto,
        sentry_evidence: Optional[dict],
    ) -> str:
        """Determine fix category for incident."""
        if incident.affected_services and len(incident.affected_services) > 1:
            return "Infrastructure / shared dependency fix"
        elif incident.alerts_count > 10:
            return "Rollback deployment / emergency fix"
        elif sentry_evidence:
            return "Code fix / defensive programming"
        else:
            return "Investigation required / multi-step fix"
    
    def _generate_summary(
        self,
        alert: AlertDto,
        sentry_evidence: Optional[dict],
    ) -> str:
        """Generate 1-2 sentence summary."""
        alert_name = alert.name or "Alert"
        service = getattr(alert, "service", "service")
        
        if sentry_evidence and sentry_evidence.get("exception_type"):
            exception_type = sentry_evidence["exception_type"]
            return (
                f"{alert_name} triggered due to {exception_type} in {service}. "
                f"Root cause likely related to code defect or runtime error."
            )
        else:
            return (
                f"{alert_name} detected in {service}. "
                f"Analysis indicates potential application or infrastructure issue requiring attention."
            )
    
    def _build_markdown_report(
        self,
        alert_name: str,
        summary: str,
        description: str,
        severity: str,
        service: str,
        source: str,
        sentry_evidence: Optional[dict],
        hypotheses: list[dict[str, str]],
        fix_category: str,
        repo: str,
    ) -> str:
        """Build full markdown RCA report."""
        report_lines = [
            f"# Root Cause Analysis: {alert_name}",
            "",
            f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"**Repository**: {repo}  ",
            f"**Severity**: {severity}  ",
            "",
            "---",
            "",
            "## Summary",
            "",
            summary,
            "",
            "## Evidence",
            "",
            f"- **Error**: {description}",
            f"- **Severity**: {severity}",
            f"- **Service**: {service}",
            f"- **Source**: {source}",
        ]
        
        if sentry_evidence:
            report_lines.extend([
                f"- **Sentry Issue**: [{sentry_evidence.get('issue_id', 'N/A')}]({sentry_evidence.get('issue_url', '')})",
                f"- **Exception Type**: {sentry_evidence.get('exception_type', 'N/A')}",
            ])
            
            if sentry_evidence.get("stacktrace_top_frame"):
                report_lines.extend([
                    f"- **Top Stack Frame**: `{sentry_evidence['stacktrace_top_frame']}`",
                ])
        
        report_lines.extend([
            "",
            "## Root Cause Hypotheses (Ranked)",
            "",
        ])
        
        for i, hypothesis in enumerate(hypotheses, 1):
            report_lines.append(
                f"{i}. **{hypothesis['likelihood']}**: {hypothesis['description']}"
            )
        
        report_lines.extend([
            "",
            "## Recommended Fix Category",
            "",
            f"**{fix_category}**",
            "",
            "### Suggested Actions",
            "",
        ])
        
        # Add specific actions based on fix category
        if "null check" in fix_category.lower():
            report_lines.extend([
                "- [ ] Review code for potential null/undefined access",
                "- [ ] Add defensive null checks and validation",
                "- [ ] Add unit tests for edge cases",
            ])
        elif "timeout" in fix_category.lower():
            report_lines.extend([
                "- [ ] Review timeout configuration",
                "- [ ] Implement retry logic with exponential backoff",
                "- [ ] Add circuit breaker pattern for external calls",
            ])
        elif "dependency" in fix_category.lower():
            report_lines.extend([
                "- [ ] Update dependency to latest stable version",
                "- [ ] Review breaking changes in changelog",
                "- [ ] Test thoroughly in staging environment",
            ])
        elif "memory" in fix_category.lower():
            report_lines.extend([
                "- [ ] Profile memory usage to identify leak",
                "- [ ] Review large object allocations",
                "- [ ] Increase heap size if needed",
            ])
        elif "rollback" in fix_category.lower():
            report_lines.extend([
                "- [ ] Rollback to previous stable version",
                "- [ ] Review deployment logs for changes",
                "- [ ] Create incident post-mortem",
            ])
        else:
            report_lines.extend([
                "- [ ] Review recent code changes",
                "- [ ] Add logging for better observability",
                "- [ ] Create comprehensive test coverage",
            ])
        
        report_lines.extend([
            "",
            "---",
            "",
            f"*This RCA was automatically generated by Keep AI Remediation.*",
        ])
        
        return "\n".join(report_lines)
    
    def _build_incident_markdown_report(
        self,
        incident_name: str,
        summary: str,
        description: str,
        severity: int,
        services: str,
        sources: str,
        alerts_count: int,
        sentry_evidence: Optional[dict],
        hypotheses: list[dict[str, str]],
        fix_category: str,
        repo: str,
    ) -> str:
        """Build markdown report for incident."""
        report_lines = [
            f"# Root Cause Analysis: {incident_name}",
            "",
            f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"**Repository**: {repo}  ",
            f"**Severity**: {severity}  ",
            f"**Affected Services**: {services}  ",
            f"**Alert Count**: {alerts_count}  ",
            "",
            "---",
            "",
            "## Summary",
            "",
            summary,
            "",
            "## Incident Details",
            "",
            f"- **Description**: {description}",
            f"- **Severity**: {severity}",
            f"- **Affected Services**: {services}",
            f"- **Sources**: {sources}",
            f"- **Total Alerts**: {alerts_count}",
        ]
        
        if sentry_evidence:
            report_lines.extend([
                "",
                "## Sentry Evidence",
                "",
                f"- **Issue**: [{sentry_evidence.get('issue_id', 'N/A')}]({sentry_evidence.get('issue_url', '')})",
                f"- **Exception Type**: {sentry_evidence.get('exception_type', 'N/A')}",
            ])
            
            if sentry_evidence.get("stacktrace_top_frame"):
                report_lines.append(f"- **Top Frame**: `{sentry_evidence['stacktrace_top_frame']}`")
        
        report_lines.extend([
            "",
            "## Root Cause Hypotheses (Ranked)",
            "",
        ])
        
        for i, hypothesis in enumerate(hypotheses, 1):
            report_lines.append(
                f"{i}. **{hypothesis['likelihood']}**: {hypothesis['description']}"
            )
        
        report_lines.extend([
            "",
            "## Recommended Fix Category",
            "",
            f"**{fix_category}**",
            "",
            "### Immediate Actions",
            "",
            "- [ ] Assess blast radius and prioritize affected services",
            "- [ ] Review recent deployments and configuration changes",
            "- [ ] Implement immediate mitigation (rollback, scaling, etc.)",
            "- [ ] Create detailed incident timeline",
            "",
            "---",
            "",
            f"*This RCA was automatically generated by Keep AI Remediation for incident with {alerts_count} alerts.*",
        ])
        
        return "\n".join(report_lines)

