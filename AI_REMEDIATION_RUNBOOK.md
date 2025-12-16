# AI Remediation Feature - Setup & Testing Runbook

## Overview

The AI Remediation feature provides automated Root Cause Analysis (RCA) and GitHub PR creation for alerts and incidents in Keep. This document describes how to enable, configure, and test the feature.

## Architecture

- **Frontend**: Button component in alert sidebar and incident header
- **Backend API**: `POST /api/ai/remediate` endpoint
- **Async Processing**: ARQ worker task for background processing
- **Storage**: Uses existing `AlertEnrichment` table (no schema migration needed)
- **Integrations**:
  - GitHub App authentication for PR creation
  - Sentry API for evidence fetching (optional)

## Prerequisites

### Required
- Keep backend running (Python 3.11+)
- Keep frontend running (Node.js 18+)
- GitHub App created and installed on target repositories

### Optional
- Redis (for async job queue; falls back to FastAPI BackgroundTasks if not available)
- Sentry account (for evidence fetching)
- Custom domain (can use AWS-generated URLs initially)

## GitHub App Setup (Optional - Skip for RCA-Only)

**For MVP**: Skip this section! GitHub PR creation is optional and disabled by default.

When you're ready to enable PR creation later, follow these steps:

<details>
<summary>Click to expand GitHub App setup instructions</summary>

### 1. Create GitHub App

1. Go to GitHub Settings → Developer settings → GitHub Apps → New GitHub App
2. Set permissions: Contents (read/write), Pull requests (read/write)
3. Generate private key and save it

### 2. Enable in Keep

Set these environment variables:
```bash
KEEP_AI_CREATE_GITHUB_PR=true
GITHUB_APP_ID=123456
GITHUB_PRIVATE_KEY_PATH=/path/to/key.pem
```

</details>

## Configuration

### Environment Variables

Add the following to your `.env` file or environment:

```bash
# Feature Flag (Required)
KEEP_ENABLE_AI_REMEDIATION=true

# GitHub App Configuration (Required)
GITHUB_APP_ID=123456
GITHUB_PRIVATE_KEY_PATH=/path/to/github-app-private-key.pem
# OR use inline key (base64 encoded):
# GITHUB_PRIVATE_KEY=LS0tLS1CRUdJTi...

# Sentry Configuration (Optional)
SENTRY_AUTH_TOKEN=sntrys_your_token_here
SENTRY_DEFAULT_ORG=your-org-slug

# Service Mapping (Optional)
# Maps service names to GitHub repositories
AI_REMEDIATION_SERVICE_MAPPING={"payments-api":"myorg/payments-service","auth-service":"myorg/auth-backend"}

# Redis (Optional but recommended)
REDIS=true
```

### Private Key Formats

The GitHub private key can be provided in two ways:

**Option 1: File path** (Recommended)
```bash
GITHUB_PRIVATE_KEY_PATH=/app/secrets/github-private-key.pem
```

**Option 2: Inline** (Base64 encoded)
```bash
# Encode the key:
cat github-private-key.pem | base64 | tr -d '\n'

# Then set:
GITHUB_PRIVATE_KEY=LS0tLS1CRUdJTiBSU0EgUFJ...
```

## Repository Resolution

The feature resolves the target GitHub repository in this priority order:

1. **Alert/Incident Tags**:
   - `repo=owner/name` tag
   - `github_repo=owner/name` tag

2. **Service Mapping** (from env var):
   - Matches alert `service` field to configured mapping

3. **Error**: If no repo is found, the job fails gracefully with an error message

### Example: Adding repo tag to an alert

Via Keep workflow or enrichment:
```yaml
actions:
  - name: enrich-with-repo
    provider:
      type: keep
      with:
        enrich:
          - key: repo
            value: myorg/my-repo
```

## Testing Locally

### 1. Start Backend

```bash
cd keep

# Minimal configuration (RCA only, no Redis)
KEEP_ENABLE_AI_REMEDIATION=true \
  python -m uvicorn keep.api.api:app --reload

# Or with Redis (recommended for production)
docker-compose up -d redis
REDIS=true KEEP_ENABLE_AI_REMEDIATION=true \
  python -m uvicorn keep.api.api:app --reload
```

### 2. Start Frontend

```bash
cd keep-ui
npm run dev
```

### 3. Start ARQ Worker (if using Redis)

```bash
cd keep
REDIS=true KEEP_ENABLE_AI_REMEDIATION=true \
  python -m keep.api.arq_worker
```

### 4. Create Test Alert

```bash
curl -X POST http://localhost:8080/api/alerts/event/keep \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: your-api-key" \
  -d '{
    "name": "Test Alert for AI Remediation",
    "description": "NullPointerException in payment processing",
    "severity": "critical",
    "service": "payments-api",
    "source": ["test"],
    "fingerprint": "test-ai-remediation-'"$(date +%s)"'"
  }'
```

### 5. Trigger AI Remediation

1. Open Keep UI: http://localhost:3000
2. Navigate to Alerts → Feed
3. Click on the test alert to open the sidebar
4. Click the "🤖 AI: Analyze Root Cause" button
5. Wait for processing (~5-10 seconds)
6. See RCA appear in the alert sidebar

### 6. Verify Results

**Check Enrichment:**
```bash
# Query the alert to see enrichment
curl http://localhost:8080/api/alerts \
  -H "X-API-KEY: your-api-key" \
  | jq '.[] | select(.fingerprint == "your-test-fingerprint") | {
      ai_remediation_status,
      ai_pr_url,
      ai_rca_summary
    }'
```

**Expected Enrichment Fields:**
```json
{
  "ai_remediation_status": "success",
  "ai_rca_summary": "Test Alert triggered due to NullPointerException...",
  "ai_rca_full_report": "# Root Cause Analysis: Test Alert\n\n## Summary\n...",
  "ai_remediation_started_at": "2025-01-15T10:30:00Z",
  "ai_remediation_completed_at": "2025-01-15T10:30:05Z"
}
```

**View RCA in UI:**
- Green success badge appears in alert sidebar
- Shows RCA summary
- Click "Re-run Analysis" to regenerate if needed

## Test Cases

### Test Case 1: Alert with `repo` tag
- **Setup**: Create alert with `repo=org/name` tag
- **Expected**: PR created successfully
- **Verify**: Check `ai_pr_url` in enrichment

### Test Case 2: Alert without repo tag
- **Setup**: Create alert without `repo` tag and no service mapping
- **Expected**: Job fails with error message
- **Verify**: Check `ai_error_message` contains "Could not determine target repository"

### Test Case 3: Alert with Sentry issue
- **Setup**: Create alert with `sentry_issue_id` field
- **Expected**: RCA includes stacktrace and exception details
- **Verify**: Check `AI_REMEDIATION.md` includes Sentry evidence

### Test Case 4: Alert without Sentry issue
- **Setup**: Create alert without `sentry_issue_id`
- **Expected**: RCA generated from alert data only
- **Verify**: RCA is still created, just without Sentry section

### Test Case 5: Incident remediation
- **Setup**: Create incident with affected services
- **Expected**: PR created with incident-level RCA
- **Verify**: Multi-service analysis in RCA report

### Test Case 6: Idempotency
- **Setup**: Click "Analyze & Create PR" button twice
- **Expected**: Second click shows "already in progress" message
- **Verify**: No duplicate PRs created

### Test Case 7: Re-run after success
- **Setup**: Complete a successful remediation, then click "Re-run Analysis"
- **Expected**: New analysis starts, new PR created
- **Verify**: Second PR in GitHub with updated analysis

## Monitoring & Debugging

### Backend Logs

Watch for log entries:
```bash
# Filter AI remediation logs
tail -f keep.log | grep "AI remediation"
```

**Key log messages:**
- `AI remediation triggered` - Request received
- `AI remediation job enqueued` - Job queued successfully
- `Processing AI remediation` - Worker started processing
- `Repository resolved` - Target repo found
- `Sentry evidence fetched` - Sentry data retrieved (if applicable)
- `RCA report generated` - Analysis complete
- `GitHub PR created` - PR created successfully
- `AI remediation completed` - Job finished

### Common Issues

#### Issue: "AI remediation feature is not enabled"
- **Cause**: Feature flag not set
- **Fix**: Set `KEEP_ENABLE_AI_REMEDIATION=true`

#### Issue: "Failed to generate JWT"
- **Cause**: Invalid GitHub private key format
- **Fix**: Verify `.pem` file format or try base64 encoding

#### Issue: "Failed to get GitHub App installation"
- **Cause**: App not installed on repository
- **Fix**: Install GitHub App on the target repository

#### Issue: "Could not determine target repository"
- **Cause**: No `repo` tag and no service mapping
- **Fix**: Add `repo=owner/name` tag to alert or configure service mapping

#### Issue: Job enqueued but never processes
- **Cause**: ARQ worker not running or misconfigured
- **Fix**: Start ARQ worker with `python -m keep.api.arq_worker`

#### Issue: "NoneType has no attribute X" in stacktrace
- **Cause**: Missing required configuration
- **Fix**: Verify all required env vars are set

## Production Deployment

### Docker Compose

Add to your `docker-compose.yml`:

```yaml
services:
  keep-backend:
    environment:
      - KEEP_ENABLE_AI_REMEDIATION=true
      - GITHUB_APP_ID=${GITHUB_APP_ID}
      - GITHUB_PRIVATE_KEY_PATH=/app/secrets/github-key.pem
      - SENTRY_AUTH_TOKEN=${SENTRY_AUTH_TOKEN}
    volumes:
      - ./secrets/github-key.pem:/app/secrets/github-key.pem:ro
    secrets:
      - github_key

secrets:
  github_key:
    file: ./secrets/github-key.pem
```

### Kubernetes

Create a Secret:
```bash
kubectl create secret generic github-app-key \
  --from-file=private-key.pem=./github-key.pem \
  -n keep
```

Update Deployment:
```yaml
spec:
  containers:
  - name: keep-backend
    env:
    - name: KEEP_ENABLE_AI_REMEDIATION
      value: "true"
    - name: GITHUB_APP_ID
      valueFrom:
        secretKeyRef:
          name: github-app-secrets
          key: app-id
    - name: GITHUB_PRIVATE_KEY_PATH
      value: /secrets/github/private-key.pem
    volumeMounts:
    - name: github-key
      mountPath: /secrets/github
      readOnly: true
  volumes:
  - name: github-key
    secret:
      secretName: github-app-key
```

## Security Considerations

1. **Never commit private keys**: Use secrets management
2. **Least privilege**: GitHub App should only have required permissions
3. **Audit logs**: Monitor GitHub App usage via GitHub audit log
4. **Draft PRs**: All PRs are created as drafts for review before merge
5. **API authentication**: Remediation endpoint requires valid Keep API key/session

## Metrics & Observability

Key metrics to monitor:
- AI remediation requests per hour
- Success rate (successful PR creation)
- Average processing time
- Failure reasons (categorized)
- Sentry evidence fetch success rate
- GitHub API rate limit usage

## Future Enhancements

Planned but not in MVP:
- LLM integration for RCA generation (replace deterministic template)
- Actual code fix generation (beyond markdown documentation)
- Support for GitLab, Bitbucket
- Auto-merge on successful CI/CD
- Feedback loop: track if PR fixed the issue

## Support

For issues or questions:
- Check backend logs for detailed error messages
- Verify all environment variables are set correctly
- Ensure GitHub App has correct permissions
- Test GitHub App authentication separately if needed

## Example RCA Output

Here's what a generated RCA report looks like:

```markdown
# Root Cause Analysis: Payment Processing Error

**Generated**: 2025-01-15 10:30:00 UTC  
**Repository**: myorg/payments-service  
**Severity**: critical  

---

## Summary

Payment Processing Error triggered due to NullPointerException in payments-api. Root cause likely related to code defect or runtime error.

## Evidence

- **Error**: NullPointerException in payment processing
- **Severity**: critical
- **Service**: payments-api
- **Source**: sentry
- **Sentry Issue**: [ISSUE-123](https://sentry.io/issues/123/)
- **Exception Type**: NullPointerException
- **Top Stack Frame**: `src/handlers/payment.py:45 in process_payment`

## Root Cause Hypotheses (Ranked)

1. **Likely**: NullPointerException indicating null/undefined access in code
2. **Possible**: External dependency failure or degraded performance
3. **Unlikely**: Configuration change or environment mismatch

## Recommended Fix Category

**Null check / defensive programming**

### Suggested Actions

- [ ] Review code for potential null/undefined access
- [ ] Add defensive null checks and validation
- [ ] Add unit tests for edge cases

---

*This RCA was automatically generated by Keep AI Remediation.*
```

## Changelog

- **v1.0.0** (2025-01-15): Initial MVP release
  - Deterministic RCA template
  - GitHub App integration
  - Sentry evidence fetching
  - Alert and incident support

