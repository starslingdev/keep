"""
GitHub PR creator using GitHub App authentication.
"""

import base64
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import jwt
import requests

from keep.api.models.ai_remediation import RCAReport

logger = logging.getLogger(__name__)


class GitHubPRCreator:
    """Creates GitHub PRs using GitHub App authentication."""
    
    GITHUB_API_BASE = "https://api.github.com"
    
    def __init__(
        self,
        app_id: str,
        private_key: Optional[str] = None,
        private_key_path: Optional[str] = None,
    ):
        """
        Initialize GitHub PR creator.
        
        Args:
            app_id: GitHub App ID
            private_key: Private key content (PEM format, can be base64 encoded)
            private_key_path: Path to private key file (if private_key not provided)
        """
        self.app_id = app_id
        self.private_key = self._load_private_key(private_key, private_key_path)
        
        if not self.private_key:
            raise ValueError(
                "GitHub private key is required. "
                "Provide either GITHUB_PRIVATE_KEY or GITHUB_PRIVATE_KEY_PATH."
            )
    
    def _load_private_key(
        self,
        private_key: Optional[str],
        private_key_path: Optional[str],
    ) -> str:
        """Load private key from string or file."""
        if private_key:
            # Try to decode from base64 if it looks encoded
            try:
                decoded = base64.b64decode(private_key).decode("utf-8")
                logger.info("Decoded private key from base64")
                return decoded
            except Exception:
                # Not base64, use as-is
                return private_key
        
        if private_key_path:
            try:
                key_path = Path(private_key_path)
                if key_path.exists():
                    return key_path.read_text()
                else:
                    logger.error(f"Private key file not found: {private_key_path}")
            except Exception as e:
                logger.exception(f"Failed to read private key file: {e}")
        
        return None
    
    def _generate_jwt(self) -> str:
        """Generate JWT for GitHub App authentication."""
        now = int(time.time())
        
        payload = {
            "iat": now - 60,  # Issued 60 seconds in the past to account for clock drift
            "exp": now + (10 * 60),  # Expires in 10 minutes
            "iss": self.app_id,
        }
        
        try:
            token = jwt.encode(payload, self.private_key, algorithm="RS256")
            return token
        except Exception as e:
            logger.exception("Failed to generate JWT")
            raise ValueError(f"Failed to generate JWT: {e}")
    
    def _get_installation_id(self, repo_owner: str, repo_name: str) -> str:
        """Get installation ID for a repository."""
        jwt_token = self._generate_jwt()
        
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        
        # Try to get installation for the repo
        url = f"{self.GITHUB_API_BASE}/repos/{repo_owner}/{repo_name}/installation"
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            installation_data = response.json()
            installation_id = installation_data["id"]
            
            logger.info(
                "Got installation ID",
                extra={"repo": f"{repo_owner}/{repo_name}", "installation_id": installation_id},
            )
            
            return str(installation_id)
            
        except requests.HTTPError as e:
            logger.exception(
                "Failed to get installation ID",
                extra={"repo": f"{repo_owner}/{repo_name}", "status": e.response.status_code},
            )
            raise ValueError(
                f"Failed to get GitHub App installation for {repo_owner}/{repo_name}. "
                "Ensure the GitHub App is installed on this repository."
            )
    
    def _get_installation_token(self, installation_id: str) -> str:
        """Get installation access token."""
        jwt_token = self._generate_jwt()
        
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        
        url = f"{self.GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
        
        try:
            response = requests.post(url, headers=headers, timeout=30)
            response.raise_for_status()
            token_data = response.json()
            
            logger.info("Got installation token", extra={"installation_id": installation_id})
            
            return token_data["token"]
            
        except requests.HTTPError as e:
            logger.exception("Failed to get installation token")
            raise ValueError(f"Failed to get installation token: {e}")
    
    def create_remediation_pr(
        self,
        repo: str,
        entity_id: str,
        entity_type: str,
        rca_report: RCAReport,
        keep_entity_link: str,
        base_branch: str = "main",
    ) -> str:
        """
        Create a draft PR with RCA and attempted fix.
        
        Args:
            repo: Repository in format "owner/name"
            entity_id: Alert fingerprint or incident ID
            entity_type: "alert" or "incident"
            rca_report: Generated RCA report
            keep_entity_link: Link back to Keep entity
            base_branch: Base branch for PR (default: main)
        
        Returns:
            PR URL
        """
        logger.info(
            "Creating remediation PR",
            extra={"repo": repo, "entity_id": entity_id, "entity_type": entity_type},
        )
        
        # Parse repo owner and name
        try:
            repo_owner, repo_name = repo.split("/")
        except ValueError:
            raise ValueError(f"Invalid repo format: {repo}. Expected 'owner/name'")
        
        # Get installation and token
        installation_id = self._get_installation_id(repo_owner, repo_name)
        access_token = self._get_installation_token(installation_id)
        
        headers = {
            "Authorization": f"token {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        
        # Get default branch (fallback if main doesn't exist)
        default_branch = self._get_default_branch(
            repo_owner, repo_name, headers, base_branch
        )
        
        # Create branch
        branch_name = self._create_branch(
            repo_owner, repo_name, entity_id, entity_type, default_branch, headers
        )
        
        # Commit RCA file
        self._commit_rca_file(
            repo_owner, repo_name, branch_name, rca_report, headers
        )
        
        # Create draft PR
        pr_url = self._create_pull_request(
            repo_owner,
            repo_name,
            branch_name,
            default_branch,
            entity_id,
            entity_type,
            rca_report,
            keep_entity_link,
            headers,
        )
        
        logger.info(
            "Remediation PR created successfully",
            extra={"repo": repo, "pr_url": pr_url},
        )
        
        return pr_url
    
    def _get_default_branch(
        self,
        repo_owner: str,
        repo_name: str,
        headers: dict,
        preferred_branch: str,
    ) -> str:
        """Get default branch or fall back to preferred."""
        url = f"{self.GITHUB_API_BASE}/repos/{repo_owner}/{repo_name}"
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            repo_data = response.json()
            default_branch = repo_data["default_branch"]
            
            logger.info(
                "Got default branch",
                extra={"repo": f"{repo_owner}/{repo_name}", "branch": default_branch},
            )
            
            return default_branch
            
        except Exception as e:
            logger.warning(
                f"Failed to get default branch, using {preferred_branch}: {e}",
            )
            return preferred_branch
    
    def _create_branch(
        self,
        repo_owner: str,
        repo_name: str,
        entity_id: str,
        entity_type: str,
        base_branch: str,
        headers: dict,
    ) -> str:
        """Create a new branch for the PR."""
        # Create branch name: keep-ai/alert-abc123-remediation or keep-ai/incident-uuid-remediation
        safe_entity_id = entity_id[:8] if len(entity_id) > 8 else entity_id
        branch_name = f"keep-ai/{entity_type}-{safe_entity_id}-remediation"
        
        logger.info(
            "Creating branch",
            extra={"repo": f"{repo_owner}/{repo_name}", "branch": branch_name},
        )
        
        # Get base branch ref
        ref_url = f"{self.GITHUB_API_BASE}/repos/{repo_owner}/{repo_name}/git/refs/heads/{base_branch}"
        
        try:
            response = requests.get(ref_url, headers=headers, timeout=30)
            response.raise_for_status()
            base_ref_data = response.json()
            base_sha = base_ref_data["object"]["sha"]
            
            # Create new ref
            create_ref_url = f"{self.GITHUB_API_BASE}/repos/{repo_owner}/{repo_name}/git/refs"
            ref_data = {
                "ref": f"refs/heads/{branch_name}",
                "sha": base_sha,
            }
            
            response = requests.post(create_ref_url, headers=headers, json=ref_data, timeout=30)
            response.raise_for_status()
            
            logger.info("Branch created successfully", extra={"branch": branch_name})
            
            return branch_name
            
        except requests.HTTPError as e:
            if e.response.status_code == 422:
                # Branch likely already exists, which is OK for idempotency
                logger.info(f"Branch {branch_name} already exists, continuing")
                return branch_name
            else:
                logger.exception("Failed to create branch")
                raise ValueError(f"Failed to create branch: {e}")
    
    def _commit_rca_file(
        self,
        repo_owner: str,
        repo_name: str,
        branch_name: str,
        rca_report: RCAReport,
        headers: dict,
    ):
        """Commit AI_REMEDIATION.md file to the branch."""
        logger.info("Committing RCA file", extra={"branch": branch_name})
        
        file_path = "AI_REMEDIATION.md"
        content = rca_report.full_report_markdown
        
        # Base64 encode content
        content_encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        # Create file
        url = f"{self.GITHUB_API_BASE}/repos/{repo_owner}/{repo_name}/contents/{file_path}"
        
        commit_data = {
            "message": f"[Keep AI] Add Root Cause Analysis for {rca_report.alert_name}",
            "content": content_encoded,
            "branch": branch_name,
        }
        
        try:
            response = requests.put(url, headers=headers, json=commit_data, timeout=30)
            response.raise_for_status()
            
            logger.info("RCA file committed successfully", extra={"file": file_path})
            
        except requests.HTTPError as e:
            logger.exception("Failed to commit RCA file")
            raise ValueError(f"Failed to commit file: {e}")
    
    def _create_pull_request(
        self,
        repo_owner: str,
        repo_name: str,
        head_branch: str,
        base_branch: str,
        entity_id: str,
        entity_type: str,
        rca_report: RCAReport,
        keep_entity_link: str,
        headers: dict,
    ) -> str:
        """Create a draft pull request."""
        logger.info("Creating pull request", extra={"head": head_branch, "base": base_branch})
        
        # Build PR title and body
        title = f"[Keep AI] Remediation for {entity_type} {entity_id[:8]}"
        
        body_lines = [
            "## 🤖 AI-Generated Remediation",
            "",
            f"This PR was automatically created by Keep AI Remediation for {entity_type}: [{entity_id}]({keep_entity_link})",
            "",
            "### 📋 Root Cause Analysis",
            "",
            rca_report.summary,
            "",
            f"**Severity**: {rca_report.severity}",
            f"**Service**: {rca_report.service}",
            "",
            "### 📄 Full Analysis",
            "",
            "See [AI_REMEDIATION.md](./AI_REMEDIATION.md) for complete Root Cause Analysis.",
            "",
            "### ✅ Next Steps",
            "",
            "1. Review the RCA report and validate the analysis",
            "2. Implement the recommended fixes (if not already included)",
            "3. Test thoroughly in a staging environment",
            "4. Update this PR with implementation details",
            "5. Request review from your team",
            "",
            "---",
            "",
            f"*Generated by [Keep](https://keephq.dev) on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}*",
        ]
        
        body = "\n".join(body_lines)
        
        url = f"{self.GITHUB_API_BASE}/repos/{repo_owner}/{repo_name}/pulls"
        
        pr_data = {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch,
            "draft": True,  # Always create as draft
            "maintainer_can_modify": True,
        }
        
        try:
            response = requests.post(url, headers=headers, json=pr_data, timeout=30)
            response.raise_for_status()
            pr_response = response.json()
            pr_url = pr_response["html_url"]
            
            logger.info("Pull request created", extra={"pr_url": pr_url})
            
            return pr_url
            
        except requests.HTTPError as e:
            logger.exception("Failed to create pull request")
            raise ValueError(f"Failed to create PR: {e}")

