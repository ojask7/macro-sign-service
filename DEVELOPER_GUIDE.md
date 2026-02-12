# Macro Sign Service - Developer Guide

> Comprehensive API reference and integration guide for developers consuming the Macro Sign Service.

**Version:** 1.0.0
**Base URL:** `http://localhost:8000/api/v1`
**Interactive Docs:** [Swagger UI](http://localhost:8000/api/docs) | [ReDoc](http://localhost:8000/api/redoc) | [OpenAPI Spec](http://localhost:8000/api/openapi.json)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Authentication](#authentication)
- [API Reference](#api-reference)
  - [Health](#health)
  - [Auth](#auth)
  - [Signing](#signing)
  - [Verification](#verification)
  - [Webhooks](#webhooks)
  - [Admin](#admin)
- [Request & Response Formats](#request--response-formats)
- [Error Handling](#error-handling)
- [Rate Limiting](#rate-limiting)
- [Webhook Events](#webhook-events)
- [File Requirements](#file-requirements)
- [SDKs & Integration Examples](#sdks--integration-examples)
- [Environment Configuration](#environment-configuration)
- [Running Tests](#running-tests)
- [Monitoring](#monitoring)

---

## Overview

Macro Sign Service is an enterprise-grade digital signing service that automates the signing and verification of Office macros (VBA). It provides:

- **Digital signing** of `.vba`, `.bas`, `.cls`, `.frm`, `.vbs` files using X.509 certificates
- **Signature verification** to validate signed macros
- **Asynchronous processing** via Celery workers for high-throughput signing
- **JWT & API key authentication** with role-based access control (RBAC)
- **Webhook notifications** for job completion events
- **Full audit trail** of all signing operations
- **Certificate management** with support for local, HashiCorp Vault, AWS KMS, and Azure Key Vault backends

---

## Architecture

```
                                +-----------------+
                                |   Dashboard     |
                                |  (Next.js:3000) |
                                +--------+--------+
                                         |
                                         v
+-------------+    REST API     +--------+--------+     Celery      +----------------+
|   Client    | +-------------> |   FastAPI API   | +-------------> | Celery Worker  |
| (curl/SDK)  |                 |   (uvicorn:8000)|                 | (signing tasks)|
+-------------+                 +--------+--------+                 +-------+--------+
                                         |                                  |
                          +--------------+--------------+                   |
                          |                             |                   |
                  +-------v-------+            +--------v------+    +-------v-------+
                  |  PostgreSQL   |            |    Redis      |    |  Cert Store   |
                  |  (port 5432)  |            |  (port 6379)  |    | (local/vault) |
                  +---------------+            +---------------+    +---------------+
```

| Service | Port | Purpose |
|---------|------|---------|
| API Server | `8000` | REST API (FastAPI + Uvicorn) |
| Dashboard | `3000` | Web management UI (Next.js) |
| PostgreSQL | `5432` | Persistent data storage |
| Redis | `6379` | Celery broker, caching, rate limiting |
| Celery Worker | -- | Async signing job processing |
| Prometheus | `9090` | Metrics collection |
| Grafana | `3001` | Monitoring dashboards |

---

## Getting Started

### Prerequisites

- Docker & Docker Compose
- (Optional) Python 3.11+ for local development

### Quick Start

```bash
# Clone the repository
git clone https://github.com/ojask7/macro-sign-service.git
cd macro-sign-service

# Copy and configure environment
cp .env.example .env

# Start all services
docker-compose up -d

# Verify services are running
docker-compose ps
```

### First API Call

```bash
# 1. Health check
curl http://localhost:8000/api/v1/health

# 2. Register a user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "dev@example.com",
    "username": "developer",
    "password": "SecurePass123!",
    "full_name": "Developer"
  }'

# 3. Login to get a token
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "developer", "password": "SecurePass123!"}'

# 4. Sign a macro file
curl -X POST http://localhost:8000/api/v1/sign \
  -H "Authorization: Bearer <your_access_token>" \
  -F "file=@your_macro.vba" \
  -F "algorithm=sha256"
```

---

## Authentication

All API endpoints (except health checks, register, and login) require authentication.

### JWT Bearer Tokens

The primary authentication method. Obtain tokens via the `/auth/login` endpoint.

```
Authorization: Bearer <access_token>
```

| Token Type | Lifetime | Purpose |
|-----------|----------|---------|
| Access Token | 30 minutes (default) | API request authentication |
| Refresh Token | 7 days (default) | Obtaining new access tokens |

### API Keys

For programmatic/CI-CD access. Create via the `/auth/api-keys` endpoint.

```
X-API-Key: mss_abc123...
```

API keys:
- Are prefixed with `mss_` for identification
- Can have optional expiration (1-365 days)
- Can be revoked at any time
- Full key is only shown **once** at creation time

### User Roles & Permissions

| Role | Permissions |
|------|------------|
| `admin` | Full access to all resources, user management, audit logs |
| `manager` | Team management, signing profiles, webhooks, analytics |
| `developer` | Sign macros, verify signatures, manage own API keys |
| `viewer` | Read-only access to job status |

---

## API Reference

### Health

#### `GET /api/v1/health` -- Health Check

Returns service health status including database and Redis connectivity.

**Authentication:** None required

**Response:**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "development",
  "timestamp": "2026-02-12T10:00:00Z",
  "checks": {
    "database": "healthy",
    "redis": "healthy"
  }
}
```

| Status | Meaning |
|--------|---------|
| `healthy` | All dependencies operational |
| `degraded` | One or more dependencies unhealthy |

#### `GET /api/v1/ready` -- Readiness Probe

Kubernetes readiness check. Returns `{"ready": true}`.

#### `GET /api/v1/live` -- Liveness Probe

Kubernetes liveness check. Returns `{"alive": true}`.

---

### Auth

#### `POST /api/v1/auth/register` -- Register User

**Authentication:** None required

**Request Body:**

```json
{
  "email": "user@example.com",
  "username": "myuser",
  "password": "SecurePass123!",
  "full_name": "John Doe"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `email` | string | Yes | Valid email, max 255 chars |
| `username` | string | Yes | 3-100 characters |
| `password` | string | Yes | Min 8 characters |
| `full_name` | string | No | Max 255 characters |

**Response: `201 Created`**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "username": "myuser",
  "full_name": "John Doe",
  "role": "developer",
  "is_active": true,
  "team_id": null,
  "created_at": "2026-02-12T10:00:00Z",
  "last_login": null
}
```

#### `POST /api/v1/auth/login` -- Login

**Request Body:**

```json
{
  "username": "myuser",
  "password": "SecurePass123!"
}
```

**Response: `200 OK`**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

#### `POST /api/v1/auth/refresh` -- Refresh Token

**Query Parameter:** `refresh_token` (string, required)

**Response: `200 OK`** -- Same format as login response with new tokens.

#### `GET /api/v1/auth/me` -- Get Current User

**Authentication:** Required

**Response: `200 OK`** -- User profile object.

#### `POST /api/v1/auth/api-keys` -- Create API Key

**Authentication:** Required

**Request Body:**

```json
{
  "name": "CI Pipeline Key",
  "expires_in_days": 90
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `name` | string | Yes | 1-100 characters |
| `expires_in_days` | integer | No | 1-365 days, null = no expiry |

**Response: `201 Created`**

```json
{
  "id": "key-uuid",
  "name": "CI Pipeline Key",
  "key_prefix": "mss_abc1",
  "api_key": "mss_abc123def456...",
  "is_active": true,
  "created_at": "2026-02-12T10:00:00Z",
  "expires_at": "2026-05-13T10:00:00Z"
}
```

> **Important:** The `api_key` field is only returned at creation time. Store it securely.

#### `GET /api/v1/auth/api-keys` -- List API Keys

**Authentication:** Required

**Response: `200 OK`** -- Array of API key objects (without the full key).

#### `DELETE /api/v1/auth/api-keys/{key_id}` -- Revoke API Key

**Authentication:** Required

**Response: `204 No Content`**

---

### Signing

#### `POST /api/v1/sign` -- Sign a Macro File

Submit a VBA macro file for digital signing. The file is processed asynchronously via a Celery worker and returns immediately with a job ID.

**Authentication:** Required (role: `developer`+)
**Content-Type:** `multipart/form-data`
**Rate Limited:** Yes

**Form Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `file` | file | Yes | -- | The macro file to sign |
| `algorithm` | string | No | `sha256` | Hash algorithm: `sha256`, `sha384`, `sha512` |
| `profile` | string | No | `null` | Signing profile name |
| `webhook_url` | string | No | `null` | URL to notify on completion |

**Example:**

```bash
curl -X POST http://localhost:8000/api/v1/sign \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@financial_report.vba" \
  -F "algorithm=sha256" \
  -F "webhook_url=https://myapp.com/hooks/signing"
```

**Response: `202 Accepted`**

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "queued",
  "original_filename": "financial_report.vba",
  "file_size": 15234,
  "file_hash": null,
  "signature": null,
  "certificate_fingerprint": null,
  "algorithm": "sha256",
  "error_message": null,
  "created_at": "2026-02-12T10:00:00Z",
  "started_at": null,
  "completed_at": null
}
```

**Job Lifecycle:**

```
queued --> processing --> completed
                    \--> failed
```

| Status | Description |
|--------|-------------|
| `queued` | Job created, waiting for worker |
| `processing` | Worker is signing the file |
| `completed` | Signing successful, signature available |
| `failed` | Signing failed, check `error_message` |

#### `GET /api/v1/sign/jobs` -- List Signing Jobs

Returns paginated list of the current user's signing jobs.

**Authentication:** Required

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | `1` | Page number |
| `per_page` | integer | `20` | Items per page |
| `status_filter` | string | `null` | Filter by status: `queued`, `processing`, `completed`, `failed` |

**Example:**

```bash
curl "http://localhost:8000/api/v1/sign/jobs?page=1&per_page=10&status_filter=completed" \
  -H "Authorization: Bearer $TOKEN"
```

**Response: `200 OK`**

```json
{
  "jobs": [
    {
      "job_id": "a1b2c3d4-...",
      "status": "completed",
      "original_filename": "report.vba",
      "file_size": 15234,
      "file_hash": "sha256:a1b2c3d4...",
      "signature": "3045022100...",
      "certificate_fingerprint": "AB:CD:EF:...",
      "algorithm": "sha256",
      "error_message": null,
      "created_at": "2026-02-12T10:00:00Z",
      "started_at": "2026-02-12T10:00:01Z",
      "completed_at": "2026-02-12T10:00:03Z"
    }
  ],
  "total": 47,
  "page": 1,
  "per_page": 10
}
```

#### `GET /api/v1/status/{job_id}` -- Check Job Status

**Authentication:** Required (owner or admin)

**Path Parameter:** `job_id` (UUID string)

**Response: `200 OK`** -- Single `SigningJobResponse` object.

When `status` is `completed`, the response includes:
- `file_hash` -- SHA hash of the original file
- `signature` -- Hex-encoded digital signature
- `certificate_fingerprint` -- SHA-256 fingerprint of the signing certificate

---

### Verification

#### `POST /api/v1/verify` -- Verify a Signed Macro

Verify the digital signature on a macro file.

**Authentication:** Required (role: `developer`+)
**Content-Type:** `multipart/form-data`
**Rate Limited:** Yes

**Form Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `file` | file | Yes | -- | The macro file to verify |
| `signature` | string | Yes | -- | Hex-encoded signature from the signing job |
| `algorithm` | string | No | `sha256` | Hash algorithm that was used for signing |

**Example:**

```bash
curl -X POST http://localhost:8000/api/v1/verify \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@financial_report.vba" \
  -F "signature=3045022100abcdef..." \
  -F "algorithm=sha256"
```

**Response: `200 OK`**

```json
{
  "is_valid": true,
  "certificate_subject": "CN=Macro Sign Service",
  "certificate_issuer": "CN=Macro Sign Service",
  "certificate_expiry": "2027-02-12T10:00:00Z",
  "message": "Signature is valid"
}
```

---

### Webhooks

Receive HTTP callbacks when signing jobs complete.

#### `POST /api/v1/webhooks` -- Create Webhook

**Authentication:** Required (permission: `manage_webhooks`)

**Request Body:**

```json
{
  "name": "Slack Notification",
  "url": "https://myapp.com/hooks/macro-sign",
  "secret": "my-webhook-secret",
  "events": "signing.completed,signing.failed"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | Yes | -- | Webhook display name (1-100 chars) |
| `url` | string | Yes | -- | HTTPS callback URL (max 2048 chars) |
| `secret` | string | No | `null` | Shared secret for HMAC signature verification |
| `events` | string | No | `signing.completed` | Comma-separated event types |

**Response: `201 Created`**

```json
{
  "id": "webhook-uuid",
  "name": "Slack Notification",
  "url": "https://myapp.com/hooks/macro-sign",
  "events": "signing.completed,signing.failed",
  "is_active": true,
  "created_at": "2026-02-12T10:00:00Z"
}
```

#### `GET /api/v1/webhooks` -- List Webhooks

**Authentication:** Required

**Response: `200 OK`** -- Array of webhook objects.

#### `PATCH /api/v1/webhooks/{webhook_id}` -- Update Webhook

**Authentication:** Required

**Request Body** (all fields optional):

```json
{
  "name": "Updated Name",
  "url": "https://new-url.com/hook",
  "events": "signing.completed",
  "is_active": false
}
```

**Response: `200 OK`** -- Updated webhook object.

#### `DELETE /api/v1/webhooks/{webhook_id}` -- Delete Webhook

**Authentication:** Required

**Response: `204 No Content`**

---

### Admin

Admin endpoints require elevated roles (`admin` or `manager`).

#### Users

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| `GET` | `/api/v1/admin/users` | `manage_users` | List all users |
| `PATCH` | `/api/v1/admin/users/{user_id}` | `manage_users` | Update user role/status/team |

#### Teams

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| `POST` | `/api/v1/admin/teams` | `manage_teams` | Create a team |
| `GET` | `/api/v1/admin/teams` | `manage_teams` | List all teams |
| `PATCH` | `/api/v1/admin/teams/{team_id}` | `manage_teams` | Update a team |

#### Signing Profiles

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| `POST` | `/api/v1/admin/profiles` | `manage_profiles` | Create signing profile |
| `GET` | `/api/v1/admin/profiles` | authenticated | List signing profiles |

#### Audit Logs

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| `GET` | `/api/v1/admin/audit` | `view_audit` | View audit logs (paginated) |

Query params: `page`, `per_page`, `action`, `resource_type`

#### Dashboard Statistics

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| `GET` | `/api/v1/admin/dashboard/stats` | `view_analytics` | Signing stats & analytics |

---

## Request & Response Formats

### Content Types

| Endpoint | Request Content-Type | Response Content-Type |
|----------|---------------------|----------------------|
| JSON endpoints | `application/json` | `application/json` |
| File upload (`/sign`, `/verify`) | `multipart/form-data` | `application/json` |

### Common Response Headers

| Header | Description |
|--------|-------------|
| `X-Request-ID` | Unique request identifier (send your own or auto-generated) |
| `X-RateLimit-Limit` | Max requests per window |
| `X-RateLimit-Remaining` | Remaining requests in window |
| `X-RateLimit-Reset` | Window reset time (Unix timestamp) |

### Pagination

Paginated endpoints return:

```json
{
  "items": [...],
  "total": 150,
  "page": 1,
  "per_page": 20
}
```

---

## Error Handling

All errors return a consistent JSON structure:

```json
{
  "detail": "Human-readable error message"
}
```

### HTTP Status Codes

| Code | Meaning | When |
|------|---------|------|
| `200` | OK | Successful request |
| `201` | Created | Resource created (register, create webhook, etc.) |
| `202` | Accepted | Signing job queued for async processing |
| `204` | No Content | Successful deletion |
| `400` | Bad Request | Invalid input, file validation error |
| `401` | Unauthorized | Missing or invalid token |
| `403` | Forbidden | Insufficient permissions |
| `404` | Not Found | Resource does not exist |
| `409` | Conflict | Duplicate resource (e.g., existing username) |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Unexpected server error |

### Common Error Responses

**Invalid credentials:**

```json
{
  "detail": "Invalid username or password"
}
```

**File validation failure:**

```json
{
  "detail": "File extension '.exe' is not allowed. Allowed: .vba, .bas, .cls, .frm, .vbs"
}
```

**Rate limited:**

```json
{
  "detail": "Rate limit exceeded. Try again in 45 seconds."
}
```

---

## Rate Limiting

The following endpoints are rate limited:

| Endpoint | Limit |
|----------|-------|
| `POST /api/v1/sign` | 60 requests/minute (default) |
| `POST /api/v1/verify` | 60 requests/minute (default) |

Rate limit headers are included in every response:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 55
X-RateLimit-Reset: 1707739200
```

When exceeded, the API returns `429 Too Many Requests`.

---

## Webhook Events

When a webhook is configured, the service sends HTTP POST requests to the registered URL on signing events.

### Event Types

| Event | Trigger |
|-------|---------|
| `signing.completed` | Job finished successfully |
| `signing.failed` | Job failed |

### Payload Format

```json
{
  "event": "signing.completed",
  "timestamp": "2026-02-12T10:00:03Z",
  "data": {
    "job_id": "a1b2c3d4-...",
    "status": "completed",
    "original_filename": "report.vba",
    "file_hash": "sha256:a1b2c3d4...",
    "signature": "3045022100...",
    "certificate_fingerprint": "AB:CD:EF:...",
    "algorithm": "sha256"
  }
}
```

### Security

If a `secret` is configured for the webhook, each request includes an HMAC-SHA256 signature header:

```
X-Webhook-Signature: sha256=<hmac_hex_digest>
```

Verify by computing `HMAC-SHA256(secret, request_body)` and comparing.

### Retry Policy

| Attempt | Delay |
|---------|-------|
| 1st retry | Immediate |
| 2nd retry | 30 seconds |
| 3rd retry | 5 minutes |
| Max retries | 3 |

Timeout: 30 seconds per attempt.

---

## File Requirements

### Supported File Types

| Extension | Description |
|-----------|-------------|
| `.vba` | VBA macro source files |
| `.bas` | VBA module files |
| `.cls` | VBA class module files |
| `.frm` | VBA form files |
| `.vbs` | VBScript files |

### Constraints

| Constraint | Value |
|-----------|-------|
| Maximum file size | 50 MB |
| Minimum file size | 1 byte (non-empty) |
| Path traversal | Rejected (`../`, absolute paths, backslashes) |
| Null bytes | Rejected |

### Content Scanning

Uploaded files are scanned for potentially dangerous patterns (e.g., `Shell()`, `WScript.Shell`, `PowerShell`, `cmd.exe`). These generate warnings in audit logs but do **not** block signing.

---

## SDKs & Integration Examples

### Python

```python
import requests

API_URL = "http://localhost:8000/api/v1"

# Login
resp = requests.post(f"{API_URL}/auth/login", json={
    "username": "developer",
    "password": "SecurePass123!"
})
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Sign a file
with open("macro.vba", "rb") as f:
    resp = requests.post(
        f"{API_URL}/sign",
        headers=headers,
        files={"file": ("macro.vba", f)},
        data={"algorithm": "sha256"},
    )
job = resp.json()
print(f"Job ID: {job['job_id']}, Status: {job['status']}")

# Poll for completion
import time
while True:
    resp = requests.get(f"{API_URL}/status/{job['job_id']}", headers=headers)
    status = resp.json()
    if status["status"] in ("completed", "failed"):
        break
    time.sleep(2)

if status["status"] == "completed":
    print(f"Signature: {status['signature']}")
    print(f"File Hash: {status['file_hash']}")

# Verify
with open("macro.vba", "rb") as f:
    resp = requests.post(
        f"{API_URL}/verify",
        headers=headers,
        files={"file": ("macro.vba", f)},
        data={
            "signature": status["signature"],
            "algorithm": "sha256",
        },
    )
print(f"Valid: {resp.json()['is_valid']}")
```

### JavaScript / Node.js

```javascript
const fs = require("fs");
const FormData = require("form-data");

const API_URL = "http://localhost:8000/api/v1";

async function signMacro() {
  // Login
  const loginResp = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "developer", password: "SecurePass123!" }),
  });
  const { access_token } = await loginResp.json();

  // Sign
  const form = new FormData();
  form.append("file", fs.createReadStream("macro.vba"));
  form.append("algorithm", "sha256");

  const signResp = await fetch(`${API_URL}/sign`, {
    method: "POST",
    headers: { Authorization: `Bearer ${access_token}`, ...form.getHeaders() },
    body: form,
  });
  const job = await signResp.json();
  console.log(`Job ${job.job_id}: ${job.status}`);

  // Poll
  let result;
  do {
    await new Promise((r) => setTimeout(r, 2000));
    const statusResp = await fetch(`${API_URL}/status/${job.job_id}`, {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    result = await statusResp.json();
  } while (!["completed", "failed"].includes(result.status));

  console.log(`Signature: ${result.signature}`);
}

signMacro();
```

### cURL (CI/CD Pipeline)

```bash
#!/bin/bash
set -e

API_URL="http://localhost:8000/api/v1"
USERNAME="ci-bot"
PASSWORD="$CI_SIGN_PASSWORD"
FILE_PATH="$1"

# Login
TOKEN=$(curl -sf -X POST "$API_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Submit signing job
JOB=$(curl -sf -X POST "$API_URL/sign" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@$FILE_PATH" \
  -F "algorithm=sha256")

JOB_ID=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "Signing job submitted: $JOB_ID"

# Poll until complete
while true; do
  STATUS=$(curl -sf "$API_URL/status/$JOB_ID" \
    -H "Authorization: Bearer $TOKEN")
  JOB_STATUS=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")

  echo "Status: $JOB_STATUS"
  [ "$JOB_STATUS" = "completed" ] && break
  [ "$JOB_STATUS" = "failed" ] && echo "FAILED" && exit 1
  sleep 2
done

# Extract signature
SIGNATURE=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin)['signature'])")
echo "Signature: $SIGNATURE"
```

### GitHub Actions

```yaml
- name: Sign VBA Macro
  run: |
    # Login
    TOKEN=$(curl -sf -X POST ${{ vars.MACRO_SIGN_URL }}/api/v1/auth/login \
      -H "Content-Type: application/json" \
      -d '{"username":"${{ secrets.SIGN_USER }}","password":"${{ secrets.SIGN_PASS }}"}' \
      | jq -r '.access_token')

    # Sign
    JOB_ID=$(curl -sf -X POST ${{ vars.MACRO_SIGN_URL }}/api/v1/sign \
      -H "Authorization: Bearer $TOKEN" \
      -F "file=@src/macros/report.vba" \
      | jq -r '.job_id')

    # Wait for completion
    for i in $(seq 1 30); do
      STATUS=$(curl -sf ${{ vars.MACRO_SIGN_URL }}/api/v1/status/$JOB_ID \
        -H "Authorization: Bearer $TOKEN" | jq -r '.status')
      [ "$STATUS" = "completed" ] && break
      [ "$STATUS" = "failed" ] && exit 1
      sleep 2
    done
```

---

## Environment Configuration

All settings are configured via environment variables or a `.env` file.

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | Environment: `development`, `staging`, `production`, `testing` |
| `APP_DEBUG` | `false` | Enable debug mode |
| `APP_SECRET_KEY` | -- | Application secret key (change in production) |
| `APP_PORT` | `8000` | API server port |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://macrosign:macrosign@localhost:5432/macrosign` | PostgreSQL connection URL |
| `DATABASE_POOL_SIZE` | `20` | Connection pool size |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | -- | JWT signing secret (change in production) |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRE_MINUTES` | `10080` | Refresh token lifetime (7 days) |

### Certificate Store

| Variable | Default | Description |
|----------|---------|-------------|
| `CERT_STORE_BACKEND` | `local` | Backend: `local`, `hashicorp_vault`, `aws_kms`, `azure_keyvault` |
| `CERT_LOCAL_CERT_PATH` | `./certs/signing_cert.pem` | Local certificate path |
| `CERT_LOCAL_KEY_PATH` | `./certs/signing_key.pem` | Local private key path |
| `VAULT_URL` | `http://localhost:8200` | HashiCorp Vault URL |
| `AWS_KMS_KEY_ID` | -- | AWS KMS key identifier |
| `AZURE_KEYVAULT_URL` | -- | Azure Key Vault URL |

### Signing

| Variable | Default | Description |
|----------|---------|-------------|
| `SIGNING_DEFAULT_ALGORITHM` | `sha256` | Default hash algorithm |
| `SIGNING_MAX_FILE_SIZE_MB` | `50` | Max upload file size in MB |
| `SIGNING_ALLOWED_EXTENSIONS` | `.vba,.bas,.cls,.frm,.vbs` | Allowed file extensions |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_ENABLED` | `true` | Enable rate limiting |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | Requests per minute per user |

### Redis & Celery

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | Celery broker URL |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/2` | Celery result backend URL |

---

## Running Tests

### Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install aiosqlite
```

### Run Tests

```bash
# All unit tests
pytest tests/unit/ -v

# Signing engine tests only
pytest tests/unit/test_signing_engine.py -v

# With coverage report
pytest tests/ -v --cov=src --cov-report=term-missing

# Specific test class
pytest tests/unit/test_signing_engine.py::TestSigning -v
```

### Test Coverage Areas

| Test Suite | File | Coverage |
|-----------|------|----------|
| Signing Engine | `test_signing_engine.py` | Sign, verify, certificates, algorithms |
| File Validator | `test_file_validator.py` | Upload validation, security checks |
| Certificate Store | `test_certificate_store.py` | Store, retrieve, rotate, delete certs |
| JWT Handler | `test_jwt_handler.py` | Token creation, verification, API keys |
| Password | `test_password.py` | Hashing and verification |
| Rate Limiter | `test_rate_limiter.py` | Request limiting |
| Settings | `test_settings.py` | Configuration loading |
| API Integration | `test_api.py` | End-to-end API tests |

---

## Monitoring

### Prometheus Metrics

Available at `GET /metrics` on the API server.

Key metrics:
- `http_requests_total` -- Total HTTP requests by method/status/path
- `http_request_duration_seconds` -- Request latency histogram
- `http_requests_in_progress` -- Current in-flight requests

### Grafana Dashboard

Access at `http://localhost:3001` (default credentials: `admin`/`admin`).

Pre-configured dashboards:
- **Macro Sign Overview** -- Request rates, latency, error rates, signing job stats

### Health Check Integration

For load balancers and container orchestration:

```bash
# Full health check (checks DB + Redis)
curl http://localhost:8000/api/v1/health

# Kubernetes readiness probe
curl http://localhost:8000/api/v1/ready

# Kubernetes liveness probe
curl http://localhost:8000/api/v1/live
```

---

## Support

- **Interactive API Docs:** `http://localhost:8000/api/docs`
- **OpenAPI Spec:** `http://localhost:8000/api/openapi.json`
- **GitHub Issues:** [github.com/ojask7/macro-sign-service/issues](https://github.com/ojask7/macro-sign-service/issues)
