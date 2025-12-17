# Testing AI RCA Locally with Sentry

## Setup (5 minutes)

### 1. Get Sentry Auth Token

1. Go to https://sentry.io/settings/account/api/auth-tokens/
2. Create new token with these scopes:
   - `project:read`
   - `event:read`
3. Copy the token (starts with `sntrys_`)

### 2. Configure Environment

```bash
cd /Users/ali/Projects/keep

# Set environment variables
export KEEP_ENABLE_AI_REMEDIATION=true
export SENTRY_AUTH_TOKEN=sntrys_your_token_here
export SENTRY_DEFAULT_ORG=your-org-slug
export AUTH_TYPE=db
export REDIS=false
```

### 3. Start Backend

```bash
cd /Users/ali/Projects/keep
poetry run uvicorn keep.api.api:app --reload --port 8080
```

### 4. Start Frontend (in another terminal)

```bash
cd /Users/ali/Projects/keep/keep-ui
npm run dev
```

## Test AI RCA

### Test 1: Simple RCA (No Sentry)

```bash
# Create a test alert
curl -X POST http://localhost:8080/api/alerts/event/keep \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: your-api-key" \
  -d '{
    "name": "Payment Processing Error",
    "description": "NullPointerException in checkout.process_payment() - user checkout failed",
    "severity": "critical",
    "service": "payments-api",
    "source": ["test"],
    "fingerprint": "test-rca-'$(date +%s)'"
  }'
```

**Then:**
1. Open http://localhost:3000
2. Go to Alerts → Feed
3. Click on "Payment Processing Error"
4. Click "🤖 AI: Analyze Root Cause"
5. Wait 5-10 seconds
6. See RCA summary appear!

**Expected RCA:**
- Summary: "Payment Processing Error detected in payments-api..."
- Hypothesis: "NullPointerException indicating null/undefined access"
- Fix: "Null check / defensive programming"

### Test 2: RCA with Sentry Evidence

**First, get a real Sentry issue ID:**

1. Go to your Sentry dashboard
2. Find any error/issue
3. Copy the issue ID (number from URL, e.g., `4506693869`)

**Create alert with Sentry ID:**

```bash
curl -X POST http://localhost:8080/api/alerts/event/keep \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: your-api-key" \
  -d '{
    "name": "Backend Error with Sentry",
    "description": "Uncaught exception in API handler",
    "severity": "high",
    "service": "backend-api",
    "source": ["sentry"],
    "sentry_issue_id": "4506693869",
    "fingerprint": "sentry-test-'$(date +%s)'"
  }'
```

**Then:**
1. Click on the alert in UI
2. Click "🤖 AI: Analyze Root Cause"
3. Wait ~10 seconds

**Expected RCA (with Sentry):**
- Summary includes exception type from Sentry
- Evidence section shows:
  - Sentry Issue link
  - Exception type
  - Top stacktrace frame
- More detailed hypotheses based on exception

### Test 3: Check RCA Data

```bash
# Query the alert to see enrichment
curl -X GET 'http://localhost:8080/api/alerts?limit=1' \
  -H "X-API-KEY: your-api-key" \
  | jq '.[0] | {
      name,
      ai_remediation_status,
      ai_rca_summary,
      ai_rca_full_report
    }'
```

**Expected output:**
```json
{
  "name": "Payment Processing Error",
  "ai_remediation_status": "success",
  "ai_rca_summary": "Payment Processing Error detected in payments-api...",
  "ai_rca_full_report": "# Root Cause Analysis: Payment Processing Error\n\n..."
}
```

## Verify Components

### Backend Logs

Watch for these log entries:

```bash
tail -f keep.log | grep -i "remediation"
```

**Expected logs:**
- `AI remediation triggered`
- `Fetching entity context`
- `Fetching Sentry evidence` (if Sentry ID provided)
- `Generating RCA report`
- `AI remediation completed successfully`

### Database Check

```bash
# Check enrichment was stored
sqlite3 keep.db "SELECT enrichments FROM alertenrichment WHERE enrichments LIKE '%ai_remediation%' ORDER BY timestamp DESC LIMIT 1;" | jq
```

## Troubleshooting

### Issue: "AI remediation feature not available"
**Fix:** Check `KEEP_ENABLE_AI_REMEDIATION=true` is set

### Issue: No Sentry evidence fetched
**Cause:** Invalid token or wrong org slug
**Fix:** Verify token has `event:read` scope

### Issue: "Could not fetch Sentry evidence"
**Cause:** Issue ID doesn't exist or wrong org
**Check logs:**
```bash
tail -f keep.log | grep Sentry
```

### Issue: Button doesn't appear
**Cause:** Feature flag not passed to frontend
**Fix:** Check backend `/healthcheck` returns `ai_remediation_enabled: true`

## What You're Testing

✅ **Backend:**
- API endpoint `/api/ai/remediate` works
- Background task executes
- RCA generator creates reports
- Sentry evidence fetcher works
- Alert enrichment updates

✅ **Frontend:**
- Button appears in alert sidebar
- Loading states work
- RCA displays in UI
- Toast notifications work

✅ **Integration:**
- Sentry API calls succeed
- Evidence enriches RCA
- Results stored in database
- UI updates automatically

## Success Criteria

- [x] Create test alert
- [x] Click AI button
- [x] See "Analyzing..." state
- [x] RCA completes in <10 seconds
- [x] Green success badge appears
- [x] RCA summary displayed
- [x] If Sentry ID provided, stacktrace included
- [x] Can re-run analysis
- [x] Database contains enrichment

**Test this while AWS deploys!** Validate the core feature works before going live. 🧪

