"""
Root Cause Analysis generator using Anthropic Claude for AI-powered analysis.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from keep.api.consts import ANTHROPIC_API_KEY, ANTHROPIC_MODEL_NAME
from keep.api.models.ai_remediation import RCAReport
from keep.api.models.alert import AlertDto
from keep.api.models.incident import IncidentDto

logger = logging.getLogger(__name__)


class RCAGenerator:
    """Generates Root Cause Analysis reports using Anthropic Claude."""
    
    def __init__(self):
        self.api_key = ANTHROPIC_API_KEY
        self.model = ANTHROPIC_MODEL_NAME
        self._client = None
        
        if self.api_key:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key)
                logger.info(f"Anthropic client initialized with model: {self.model}")
            except ImportError:
                logger.warning("anthropic package not installed, falling back to template-based RCA")
            except Exception as e:
                logger.warning(f"Failed to initialize Anthropic client: {e}")
        else:
            logger.info("ANTHROPIC_API_KEY not configured, using template-based RCA")
    
    def generate_rca_report(
        self,
        alert: AlertDto,
        sentry_evidence: Optional[dict],
        repo: str,
    ) -> RCAReport:
        """
        Generate RCA report for an alert using AI.
        
        Args:
            alert: Alert to analyze
            sentry_evidence: Optional Sentry evidence dict
            repo: Target repository (owner/name)
        
        Returns:
            RCAReport with AI-generated analysis
        """
        logger.info(
            "Generating RCA report for alert",
            extra={"alert_name": alert.name, "repo": repo, "using_ai": bool(self._client)},
        )
        
        if self._client:
            return self._generate_ai_rca_report(alert, sentry_evidence, repo)
        else:
            return self._generate_template_rca_report(alert, sentry_evidence, repo)
    
    def generate_incident_rca_report(
        self,
        incident: IncidentDto,
        sentry_evidence: Optional[dict],
        repo: str,
    ) -> RCAReport:
        """
        Generate RCA report for an incident using AI.
        
        Args:
            incident: Incident to analyze
            sentry_evidence: Optional Sentry evidence dict
            repo: Target repository (owner/name)
        
        Returns:
            RCAReport with AI-generated analysis
        """
        logger.info(
            "Generating RCA report for incident",
            extra={"incident_id": incident.id, "repo": repo, "using_ai": bool(self._client)},
        )
        
        if self._client:
            return self._generate_ai_incident_rca_report(incident, sentry_evidence, repo)
        else:
            return self._generate_template_incident_rca_report(incident, sentry_evidence, repo)
    
    def _generate_ai_rca_report(
        self,
        alert: AlertDto,
        sentry_evidence: Optional[dict],
        repo: str,
    ) -> RCAReport:
        """Generate RCA using Anthropic Claude."""
        alert_name = alert.name or "Unnamed Alert"
        severity = getattr(alert, "severity", "unknown")
        service = getattr(alert, "service", "unknown")
        description = getattr(alert, "description", "No description available")
        source = alert.source[0] if alert.source else "unknown"
        
        # Build context for Claude
        alert_context = {
            "name": alert_name,
            "severity": str(severity),
            "service": service,
            "description": description,
            "source": source,
            "fingerprint": alert.fingerprint,
        }
        
        # Add any additional alert fields that might be useful
        if hasattr(alert, "event") and isinstance(alert.event, dict):
            # Include relevant event data but limit size
            event_keys = ["message", "error", "exception", "stack", "labels", "annotations"]
            for key in event_keys:
                if key in alert.event:
                    alert_context[key] = str(alert.event[key])[:1000]  # Limit size
        
        prompt = self._build_rca_prompt(alert_context, sentry_evidence, repo)
        
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
                system=self._get_system_prompt(),
            )
            
            content = response.content[0].text
            logger.debug("Received AI response", extra={"response_length": len(content)})
            
            # Parse the JSON response
            rca_data = self._parse_ai_response(content)
            
            # Build the full markdown report
            markdown_report = self._build_ai_markdown_report(
                alert_name=alert_name,
                severity=str(severity),
                service=service,
                source=source,
                repo=repo,
                rca_data=rca_data,
                sentry_evidence=sentry_evidence,
            )
            
            return RCAReport(
                summary=rca_data.get("summary", f"AI analysis of {alert_name}"),
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
                hypotheses=rca_data.get("hypotheses", []),
                recommended_fix_category=rca_data.get("recommended_fix_category", "Code fix"),
                full_report_markdown=markdown_report,
                generated_at=datetime.utcnow(),
            )
            
        except Exception as e:
            logger.exception("AI RCA generation failed, falling back to template")
            return self._generate_template_rca_report(alert, sentry_evidence, repo)
    
    def _generate_ai_incident_rca_report(
        self,
        incident: IncidentDto,
        sentry_evidence: Optional[dict],
        repo: str,
    ) -> RCAReport:
        """Generate incident RCA using Anthropic Claude."""
        incident_name = incident.user_generated_name or incident.ai_generated_name or f"Incident #{incident.id}"
        severity = incident.severity
        services = ", ".join(incident.affected_services) if incident.affected_services else "unknown"
        description = incident.user_summary or incident.generated_summary or "No description available"
        sources = ", ".join(incident.sources) if incident.sources else "unknown"
        
        incident_context = {
            "name": incident_name,
            "severity": str(severity),
            "services": services,
            "description": description,
            "sources": sources,
            "alerts_count": incident.alerts_count,
        }
        
        prompt = self._build_incident_rca_prompt(incident_context, sentry_evidence, repo)
        
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
                system=self._get_system_prompt(),
            )
            
            content = response.content[0].text
            rca_data = self._parse_ai_response(content)
            
            markdown_report = self._build_ai_incident_markdown_report(
                incident_name=incident_name,
                severity=severity,
                services=services,
                sources=sources,
                alerts_count=incident.alerts_count,
                repo=repo,
                rca_data=rca_data,
                sentry_evidence=sentry_evidence,
            )
            
            return RCAReport(
                summary=rca_data.get("summary", f"AI analysis of {incident_name}"),
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
                hypotheses=rca_data.get("hypotheses", []),
                recommended_fix_category=rca_data.get("recommended_fix_category", "Investigation required"),
                full_report_markdown=markdown_report,
                generated_at=datetime.utcnow(),
            )
            
        except Exception as e:
            logger.exception("AI incident RCA generation failed, falling back to template")
            return self._generate_template_incident_rca_report(incident, sentry_evidence, repo)
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for Claude."""
        return """You are an expert Site Reliability Engineer (SRE) and incident response specialist.
Your task is to analyze alerts and incidents to provide actionable Root Cause Analysis (RCA) reports.

You must respond with valid JSON containing the following fields:
{
    "summary": "A concise 1-2 sentence summary of the issue and likely root cause",
    "root_cause_analysis": "Detailed analysis of what went wrong and why",
    "hypotheses": [
        {
            "likelihood": "Likely|Possible|Unlikely",
            "description": "Description of this hypothesis",
            "evidence": "What evidence supports or refutes this hypothesis"
        }
    ],
    "recommended_fix_category": "One of: Code fix, Configuration change, Infrastructure scaling, Dependency update, Rollback, Monitoring improvement",
    "immediate_actions": ["List of immediate actions to take"],
    "long_term_recommendations": ["List of long-term improvements to prevent recurrence"],
    "investigation_steps": ["Steps to further investigate if root cause is unclear"]
}

Be specific, actionable, and prioritize based on likelihood and impact.
Consider common failure modes: null pointer exceptions, timeouts, resource exhaustion, configuration drift, dependency failures, race conditions, and capacity issues."""
    
    def _build_rca_prompt(
        self,
        alert_context: dict,
        sentry_evidence: Optional[dict],
        repo: str,
    ) -> str:
        """Build the prompt for alert RCA."""
        prompt = f"""Analyze this alert and provide a Root Cause Analysis:

## Alert Information
- **Name**: {alert_context.get('name')}
- **Severity**: {alert_context.get('severity')}
- **Service**: {alert_context.get('service')}
- **Source**: {alert_context.get('source')}
- **Description**: {alert_context.get('description')}
"""
        
        if alert_context.get('message'):
            prompt += f"- **Message**: {alert_context.get('message')}\n"
        
        if alert_context.get('error'):
            prompt += f"- **Error**: {alert_context.get('error')}\n"
        
        if sentry_evidence:
            prompt += f"""
## Sentry Evidence
- **Issue ID**: {sentry_evidence.get('issue_id', 'N/A')}
- **Exception Type**: {sentry_evidence.get('exception_type', 'N/A')}
- **Message**: {sentry_evidence.get('message', 'N/A')}
- **Top Stack Frame**: {sentry_evidence.get('stacktrace_top_frame', 'N/A')}
"""
        
        if repo and repo != "N/A":
            prompt += f"\n## Repository\n- **Target Repo**: {repo}\n"
        
        prompt += "\nProvide your analysis as JSON."
        
        return prompt
    
    def _build_incident_rca_prompt(
        self,
        incident_context: dict,
        sentry_evidence: Optional[dict],
        repo: str,
    ) -> str:
        """Build the prompt for incident RCA."""
        prompt = f"""Analyze this incident and provide a Root Cause Analysis:

## Incident Information
- **Name**: {incident_context.get('name')}
- **Severity**: {incident_context.get('severity')}
- **Affected Services**: {incident_context.get('services')}
- **Sources**: {incident_context.get('sources')}
- **Alert Count**: {incident_context.get('alerts_count')}
- **Description**: {incident_context.get('description')}
"""
        
        if sentry_evidence:
            prompt += f"""
## Sentry Evidence
- **Issue ID**: {sentry_evidence.get('issue_id', 'N/A')}
- **Exception Type**: {sentry_evidence.get('exception_type', 'N/A')}
- **Top Stack Frame**: {sentry_evidence.get('stacktrace_top_frame', 'N/A')}
"""
        
        if repo and repo != "N/A":
            prompt += f"\n## Repository\n- **Target Repo**: {repo}\n"
        
        prompt += "\nProvide your analysis as JSON."
        
        return prompt
    
    def _parse_ai_response(self, content: str) -> dict:
        """Parse Claude's JSON response."""
        try:
            # Try to extract JSON from the response
            # Claude might wrap it in markdown code blocks
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                content = content[start:end].strip()
            elif "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                content = content[start:end].strip()
            
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse AI response as JSON: {e}")
            # Return a basic structure with the raw content
            return {
                "summary": "AI analysis completed (see full report)",
                "root_cause_analysis": content,
                "hypotheses": [
                    {"likelihood": "Possible", "description": "See detailed analysis", "evidence": "N/A"}
                ],
                "recommended_fix_category": "Investigation required",
                "immediate_actions": ["Review the detailed analysis below"],
                "long_term_recommendations": [],
                "investigation_steps": [],
            }
    
    def _build_ai_markdown_report(
        self,
        alert_name: str,
        severity: str,
        service: str,
        source: str,
        repo: str,
        rca_data: dict,
        sentry_evidence: Optional[dict],
    ) -> str:
        """Build markdown report from AI analysis."""
        report_lines = [
            f"# Root Cause Analysis: {alert_name}",
            "",
            f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"**Analyzed by**: Claude ({self.model})  ",
            f"**Severity**: {severity}  ",
            f"**Service**: {service}  ",
            "",
            "---",
            "",
            "## Summary",
            "",
            rca_data.get("summary", "No summary available"),
            "",
            "## Root Cause Analysis",
            "",
            rca_data.get("root_cause_analysis", "Analysis not available"),
            "",
        ]
        
        # Hypotheses
        hypotheses = rca_data.get("hypotheses", [])
        if hypotheses:
            report_lines.extend([
                "## Root Cause Hypotheses (Ranked by Likelihood)",
                "",
            ])
            for i, hypothesis in enumerate(hypotheses, 1):
                likelihood = hypothesis.get("likelihood", "Unknown")
                description = hypothesis.get("description", "No description")
                evidence = hypothesis.get("evidence", "")
                report_lines.append(f"{i}. **{likelihood}**: {description}")
                if evidence:
                    report_lines.append(f"   - *Evidence*: {evidence}")
            report_lines.append("")
        
        # Evidence section
        report_lines.extend([
            "## Evidence",
            "",
            f"- **Alert Source**: {source}",
            f"- **Service**: {service}",
            f"- **Severity**: {severity}",
        ])
        
        if sentry_evidence:
            report_lines.extend([
                f"- **Sentry Issue**: [{sentry_evidence.get('issue_id', 'N/A')}]({sentry_evidence.get('issue_url', '')})",
                f"- **Exception Type**: {sentry_evidence.get('exception_type', 'N/A')}",
            ])
            if sentry_evidence.get("stacktrace_top_frame"):
                report_lines.append(f"- **Top Stack Frame**: `{sentry_evidence['stacktrace_top_frame']}`")
        
        report_lines.append("")
        
        # Recommended fix
        report_lines.extend([
            "## Recommended Fix Category",
            "",
            f"**{rca_data.get('recommended_fix_category', 'Investigation required')}**",
            "",
        ])
        
        # Immediate actions
        immediate_actions = rca_data.get("immediate_actions", [])
        if immediate_actions:
            report_lines.extend([
                "## Immediate Actions",
                "",
            ])
            for action in immediate_actions:
                report_lines.append(f"- [ ] {action}")
            report_lines.append("")
        
        # Investigation steps
        investigation_steps = rca_data.get("investigation_steps", [])
        if investigation_steps:
            report_lines.extend([
                "## Investigation Steps",
                "",
            ])
            for step in investigation_steps:
                report_lines.append(f"- [ ] {step}")
            report_lines.append("")
        
        # Long-term recommendations
        long_term = rca_data.get("long_term_recommendations", [])
        if long_term:
            report_lines.extend([
                "## Long-term Recommendations",
                "",
            ])
            for rec in long_term:
                report_lines.append(f"- {rec}")
            report_lines.append("")
        
        report_lines.extend([
            "---",
            "",
            f"*This RCA was generated by Keep AI Remediation using {self.model}.*",
        ])
        
        return "\n".join(report_lines)
    
    def _build_ai_incident_markdown_report(
        self,
        incident_name: str,
        severity: int,
        services: str,
        sources: str,
        alerts_count: int,
        repo: str,
        rca_data: dict,
        sentry_evidence: Optional[dict],
    ) -> str:
        """Build markdown report for incident from AI analysis."""
        report_lines = [
            f"# Root Cause Analysis: {incident_name}",
            "",
            f"**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"**Analyzed by**: Claude ({self.model})  ",
            f"**Severity**: {severity}  ",
            f"**Affected Services**: {services}  ",
            f"**Alert Count**: {alerts_count}  ",
            "",
            "---",
            "",
            "## Summary",
            "",
            rca_data.get("summary", "No summary available"),
            "",
            "## Root Cause Analysis",
            "",
            rca_data.get("root_cause_analysis", "Analysis not available"),
            "",
        ]
        
        # Hypotheses
        hypotheses = rca_data.get("hypotheses", [])
        if hypotheses:
            report_lines.extend([
                "## Root Cause Hypotheses (Ranked by Likelihood)",
                "",
            ])
            for i, hypothesis in enumerate(hypotheses, 1):
                likelihood = hypothesis.get("likelihood", "Unknown")
                description = hypothesis.get("description", "No description")
                evidence = hypothesis.get("evidence", "")
                report_lines.append(f"{i}. **{likelihood}**: {description}")
                if evidence:
                    report_lines.append(f"   - *Evidence*: {evidence}")
            report_lines.append("")
        
        # Evidence section
        report_lines.extend([
            "## Incident Details",
            "",
            f"- **Sources**: {sources}",
            f"- **Affected Services**: {services}",
            f"- **Severity**: {severity}",
            f"- **Total Alerts**: {alerts_count}",
        ])
        
        if sentry_evidence:
            report_lines.extend([
                "",
                "### Sentry Evidence",
                "",
                f"- **Issue**: [{sentry_evidence.get('issue_id', 'N/A')}]({sentry_evidence.get('issue_url', '')})",
                f"- **Exception Type**: {sentry_evidence.get('exception_type', 'N/A')}",
            ])
            if sentry_evidence.get("stacktrace_top_frame"):
                report_lines.append(f"- **Top Frame**: `{sentry_evidence['stacktrace_top_frame']}`")
        
        report_lines.append("")
        
        # Recommended fix
        report_lines.extend([
            "## Recommended Fix Category",
            "",
            f"**{rca_data.get('recommended_fix_category', 'Investigation required')}**",
            "",
        ])
        
        # Immediate actions
        immediate_actions = rca_data.get("immediate_actions", [])
        if immediate_actions:
            report_lines.extend([
                "## Immediate Actions",
                "",
            ])
            for action in immediate_actions:
                report_lines.append(f"- [ ] {action}")
            report_lines.append("")
        
        # Investigation steps
        investigation_steps = rca_data.get("investigation_steps", [])
        if investigation_steps:
            report_lines.extend([
                "## Investigation Steps",
                "",
            ])
            for step in investigation_steps:
                report_lines.append(f"- [ ] {step}")
            report_lines.append("")
        
        # Long-term recommendations
        long_term = rca_data.get("long_term_recommendations", [])
        if long_term:
            report_lines.extend([
                "## Long-term Recommendations",
                "",
            ])
            for rec in long_term:
                report_lines.append(f"- {rec}")
            report_lines.append("")
        
        report_lines.extend([
            "---",
            "",
            f"*This RCA was generated by Keep AI Remediation using {self.model} for incident with {alerts_count} alerts.*",
        ])
        
        return "\n".join(report_lines)
    
    # =========================================================================
    # Template-based fallback methods (when no API key is configured)
    # =========================================================================
    
    def _generate_template_rca_report(
        self,
        alert: AlertDto,
        sentry_evidence: Optional[dict],
        repo: str,
    ) -> RCAReport:
        """Generate RCA using deterministic templates (fallback)."""
        alert_name = alert.name or "Unnamed Alert"
        severity = getattr(alert, "severity", "unknown")
        service = getattr(alert, "service", "unknown")
        description = getattr(alert, "description", "No description available")
        source = alert.source[0] if alert.source else "unknown"
        
        hypotheses = self._generate_template_hypotheses(alert, sentry_evidence)
        fix_category = self._determine_fix_category(alert, sentry_evidence)
        summary = self._generate_template_summary(alert, sentry_evidence)
        
        markdown_report = self._build_template_markdown_report(
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
    
    def _generate_template_incident_rca_report(
        self,
        incident: IncidentDto,
        sentry_evidence: Optional[dict],
        repo: str,
    ) -> RCAReport:
        """Generate incident RCA using templates (fallback)."""
        incident_name = incident.user_generated_name or incident.ai_generated_name or f"Incident #{incident.id}"
        severity = incident.severity
        services = ", ".join(incident.affected_services) if incident.affected_services else "unknown"
        description = incident.user_summary or incident.generated_summary or "No description available"
        
        hypotheses = self._generate_template_incident_hypotheses(incident, sentry_evidence)
        fix_category = self._determine_incident_fix_category(incident, sentry_evidence)
        
        summary = (
            f"Incident affecting {services} with severity {severity}. "
            f"Analysis suggests {fix_category.lower()} as primary remediation approach."
        )
        
        markdown_report = f"""# Root Cause Analysis: {incident_name}

**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}  
**Severity**: {severity}  
**Affected Services**: {services}  

---

## Summary

{summary}

## Note

Configure `ANTHROPIC_API_KEY` for AI-powered analysis.

---

*Template-based RCA - configure ANTHROPIC_API_KEY for AI-powered analysis.*
"""
        
        return RCAReport(
            summary=summary,
            alert_name=incident_name,
            alert_id=str(incident.id),
            severity=str(severity),
            service=services,
            error_description=description,
            sentry_issue_id=sentry_evidence.get("issue_id") if sentry_evidence else None,
            stacktrace_top_frame=None,
            hypotheses=hypotheses,
            recommended_fix_category=fix_category,
            full_report_markdown=markdown_report,
            generated_at=datetime.utcnow(),
        )
    
    def _generate_template_hypotheses(
        self,
        alert: AlertDto,
        sentry_evidence: Optional[dict],
    ) -> list[dict[str, str]]:
        """Generate basic hypotheses from patterns."""
        hypotheses = []
        description_lower = getattr(alert, "description", "").lower()
        
        if sentry_evidence and sentry_evidence.get("exception_type"):
            hypotheses.append({
                "likelihood": "Likely",
                "description": f"{sentry_evidence['exception_type']} exception in application code",
            })
        elif "timeout" in description_lower:
            hypotheses.append({
                "likelihood": "Likely",
                "description": "Connection timeout or slow external dependency",
            })
        else:
            hypotheses.append({
                "likelihood": "Possible",
                "description": "Application logic error or unexpected state",
            })
        
        return hypotheses
    
    def _generate_template_incident_hypotheses(
        self,
        incident: IncidentDto,
        sentry_evidence: Optional[dict],
    ) -> list[dict[str, str]]:
        """Generate hypotheses for incident."""
        hypotheses = []
        
        if incident.affected_services and len(incident.affected_services) > 1:
            hypotheses.append({
                "likelihood": "Likely",
                "description": f"Shared infrastructure issue affecting {len(incident.affected_services)} services",
            })
        else:
            hypotheses.append({
                "likelihood": "Possible",
                "description": "Application-level issue requiring investigation",
            })
        
        return hypotheses
    
    def _determine_fix_category(
        self,
        alert: AlertDto,
        sentry_evidence: Optional[dict],
    ) -> str:
        """Determine fix category from patterns."""
        description_lower = getattr(alert, "description", "").lower()
        
        if "timeout" in description_lower:
            return "Timeout / retry configuration"
        elif "memory" in description_lower:
            return "Memory optimization"
        else:
            return "Code fix / investigation"
    
    def _determine_incident_fix_category(
        self,
        incident: IncidentDto,
        sentry_evidence: Optional[dict],
    ) -> str:
        """Determine fix category for incident."""
        if incident.affected_services and len(incident.affected_services) > 1:
            return "Infrastructure / shared dependency fix"
        elif incident.alerts_count > 10:
            return "Rollback / emergency fix"
        else:
            return "Investigation required"
    
    def _generate_template_summary(
        self,
        alert: AlertDto,
        sentry_evidence: Optional[dict],
    ) -> str:
        """Generate summary from patterns."""
        alert_name = alert.name or "Alert"
        service = getattr(alert, "service", "service")
        
        if sentry_evidence and sentry_evidence.get("exception_type"):
            return f"{alert_name} triggered due to {sentry_evidence['exception_type']} in {service}."
        else:
            return f"{alert_name} detected in {service}. Configure ANTHROPIC_API_KEY for AI-powered analysis."
    
    def _build_template_markdown_report(
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
        """Build template-based markdown report."""
        return f"""# Root Cause Analysis: {alert_name}

**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}  
**Severity**: {severity}  
**Service**: {service}  

---

## Summary

{summary}

## Evidence

- **Error**: {description}
- **Severity**: {severity}
- **Service**: {service}
- **Source**: {source}

## Recommended Fix Category

**{fix_category}**

## Note

Configure `ANTHROPIC_API_KEY` environment variable for AI-powered root cause analysis with detailed hypotheses and actionable recommendations.

---

*Template-based RCA - configure ANTHROPIC_API_KEY for AI-powered analysis.*
"""
