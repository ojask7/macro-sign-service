# Macro Sign Service — API Documentation

## Base URL

```
http://localhost:8000/api/v1
```

## Authentication

All endpoints except health checks, register, and login require authentication.

### JWT Bearer Token

```
Authorization: Bearer <your-jwt-token>
```

### API Key

```
X-API-Key: mss_<your-api-key>
```

---

## Endpoint Overview

### ServiceNow Integration (Synchronous)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/snow/sign` | Required | Sign a macro and return signed content immediately (200 OK) |
| POST | `/snow/verify` | Required | Verify a previously signed macro |
| GET | `/snow/certs` | Required | List available certificates in the key store |

### Standard Signing (Asynchronous)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/sign` | Required | Submit a macro for async signing — returns job_id (202 Accepted) |
| GET | `/sign/jobs` | Required | List the current user's signing jobs |
| GET | `/status/{job_id}` | Required | Poll a signing job's status |
| POST | `/verify` | Required | Verify a signed macro |

### Other

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | None | Full health check |
| GET | `/ready` | None | Kubernetes readiness probe |
| GET | `/live` | None | Kubernetes liveness probe |
| POST | `/auth/register` | None | Register a new user |
| POST | `/auth/login` | None | Login and receive JWT tokens |
| POST | `/auth/refresh` | None | Refresh access token |
| GET | `/auth/me` | Required | Get current user profile |
| POST | `/auth/api-keys` | Required | Create an API key |
| GET | `/auth/api-keys` | Required | List API keys |
| DELETE | `/auth/api-keys/{id}` | Required | Revoke an API key |
| POST | `/webhooks` | Required | Create a webhook |
| GET | `/webhooks` | Required | List webhooks |
| PATCH | `/webhooks/{id}` | Required | Update a webhook |
| DELETE | `/webhooks/{id}` | Required | Delete a webhook |
| GET | `/admin/users` | admin | List all users |
| PATCH | `/admin/users/{id}` | admin | Update a user |
| POST | `/admin/teams` | manager+ | Create a team |
| GET | `/admin/teams` | manager+ | List teams |
| POST | `/admin/profiles` | manager+ | Create signing profile |
| GET | `/admin/profiles` | authenticated | List signing profiles |
| GET | `/admin/audit` | view_audit | View audit logs |
| GET | `/admin/dashboard/stats` | view_analytics | Dashboard statistics |

---

## ServiceNow Integration Endpoints

The SNOW endpoints are designed for **synchronous** usage: the caller receives signed content in a single HTTP round-trip with no polling. The test-domain certificate (`snow-test-domain`) is auto-provisioned on first use.

### `POST /api/v1/snow/sign`

Sign a macro file and return the signed content directly to the ServiceNow form.

**Authentication:** Required (role: `developer`+)
**Content-Type:** `multipart/form-data`

**Form Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `file` | file | Yes | — | Macro file to sign (.vba, .bas, .cls, .frm, .vbs) |
| `algorithm` | string | No | `sha256` | Hash algorithm: `sha256`, `sha384`, `sha512` |
| `domain` | string | No | `snow-test-domain` | Certificate name in the key store |
| `requester_id` | string | No | `null` | ServiceNow sys_id of the requesting user (stored in audit log) |
| `table` | string | No | `null` | ServiceNow table name (stored in audit log) |

**Example:**

```bash
curl -X POST http://localhost:8000/api/v1/snow/sign \
  -H "X-API-Key: mss_your_key" \
  -F "file=@report_macro.vba" \
  -F "algorithm=sha256" \
  -F "requester_id=sys_u_abc123" \
  -F "table=sys_script_include"
```

**Response: `200 OK`**

```json
{
  "status": "signed",
  "original_filename": "report_macro.vba",
  "file_size": 2048,
  "signed_content_b64": "QXR0cmlidXRlIFZCX05hbWUg...",
  "signature": "3045022100abcdef1234...",
  "file_hash": "a1b2c3d4e5f6...",
  "certificate_fingerprint": "AB:CD:EF:01:23:...",
  "certificate_subject": "CN=snow-test.macro-sign.local,O=SNOW Test Domain,C=US",
  "certificate_pem": "-----BEGIN CERTIFICATE-----\nMIIC...\n-----END CERTIFICATE-----\n",
  "algorithm": "sha256",
  "signed_at": "2026-02-23T10:00:00Z",
  "requester_id": "sys_u_abc123",
  "domain": "snow-test-domain"
}
```

**Response Fields:**

| Field | Description |
|-------|-------------|
| `signed_content_b64` | Base64-encoded original file bytes — SNOW stores this in a record field |
| `signature` | Hex-encoded RSA/ECDSA digital signature — SNOW stores this for later verification |
| `certificate_pem` | PEM-encoded public certificate — can be used for client-side verification |
| `certificate_subject` | X.509 subject string of the signing certificate |
| `certificate_fingerprint` | SHA-256 fingerprint of the signing certificate |
| `requester_id` | Echoed back from the request for SNOW form tracking |

**Error Responses:**

| Code | Reason |
|------|--------|
| `400` | Invalid file extension, file empty, file too large, path traversal detected |
| `401` | Missing or invalid authentication |
| `403` | Insufficient permissions |
| `503` | Certificate not available in the key store |

---

### `POST /api/v1/snow/verify`

Verify the digital signature on a previously signed macro.

**Authentication:** Required (role: `developer`+)
**Content-Type:** `multipart/form-data`

**Form Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `file` | file | Yes | — | The original macro file to verify |
| `signature` | string | Yes | — | Hex-encoded signature from the sign response |
| `algorithm` | string | No | `sha256` | Hash algorithm used during signing |
| `domain` | string | No | `snow-test-domain` | Certificate domain used when signing |

**Example:**

```bash
curl -X POST http://localhost:8000/api/v1/snow/verify \
  -H "X-API-Key: mss_your_key" \
  -F "file=@report_macro.vba" \
  -F "signature=3045022100abcdef..." \
  -F "algorithm=sha256" \
  -F "domain=snow-test-domain"
```

**Response: `200 OK`**

```json
{
  "is_valid": true,
  "certificate_subject": "CN=snow-test.macro-sign.local,O=SNOW Test Domain,C=US",
  "certificate_issuer": "CN=snow-test.macro-sign.local,O=SNOW Test Domain,C=US",
  "certificate_expiry": "2027-02-23T10:00:00Z",
  "message": "Signature is valid",
  "domain": "snow-test-domain"
}
```

---

### `GET /api/v1/snow/certs`

List all certificates available in the configured key store.

**Authentication:** Required (role: `developer`+)

**Response: `200 OK`**

```json
{
  "certificates": ["default", "snow-test-domain", "production"],
  "count": 3
}
```

---

## Standard Signing Endpoints

### `POST /api/v1/sign`

Submit a macro file for asynchronous signing. Processing is handled by a Celery worker. Use this for CI/CD pipelines and batch workloads where polling is acceptable.

**Authentication:** Required (role: `developer`+)
**Content-Type:** `multipart/form-data`
**Rate Limited:** Yes

**Form Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `file` | file | Yes | — | Macro file (.vba, .bas, .cls, .frm, .vbs) |
| `algorithm` | string | No | `sha256` | Hash algorithm |
| `profile` | string | No | `null` | Signing profile name |
| `webhook_url` | string | No | `null` | URL to POST a callback on completion |

**Response: `202 Accepted`**

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "queued",
  "original_filename": "report.vba",
  "file_size": 15234,
  "algorithm": "sha256",
  "created_at": "2026-02-23T10:00:00Z"
}
```

**Job Lifecycle:** `queued` → `processing` → `completed` | `failed`

---

### `GET /api/v1/status/{job_id}`

Poll the status of a signing job.

**Response: `200 OK`** (when completed):

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "completed",
  "original_filename": "report.vba",
  "file_size": 15234,
  "file_hash": "a1b2c3d4...",
  "signature": "3045022100...",
  "certificate_fingerprint": "AB:CD:EF:...",
  "algorithm": "sha256",
  "created_at": "2026-02-23T10:00:00Z",
  "started_at": "2026-02-23T10:00:01Z",
  "completed_at": "2026-02-23T10:00:02Z"
}
```

---

### `POST /api/v1/verify`

Verify a signed macro file against the default signing certificate.

**Form Fields:** `file` (required), `signature` (required, hex), `algorithm` (optional, default `sha256`)

**Response: `200 OK`**

```json
{
  "is_valid": true,
  "certificate_subject": "CN=Macro Sign Service",
  "certificate_issuer": "CN=Macro Sign Service",
  "certificate_expiry": "2027-02-23T00:00:00Z",
  "message": "Signature is valid"
}
```

---

## Authentication Endpoints

### `POST /api/v1/auth/register`

```json
{
  "email": "user@example.com",
  "username": "myuser",
  "password": "SecurePass123!",
  "full_name": "John Doe"
}
```

**Response: `201 Created`** — User profile object.

### `POST /api/v1/auth/login`

```json
{ "username": "myuser", "password": "SecurePass123!" }
```

**Response: `200 OK`**

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### `POST /api/v1/auth/api-keys`

```json
{ "name": "CI Pipeline Key", "expires_in_days": 90 }
```

**Response: `201 Created`** — includes `api_key` (shown once only).

---

## Webhooks

Webhooks fire on `signing.completed` and `signing.failed` events.

**Payload:**
```json
{
  "event": "signing.completed",
  "timestamp": "2026-02-23T10:00:03Z",
  "data": {
    "job_id": "a1b2c3d4-...",
    "status": "completed",
    "signature": "3045022100...",
    "file_hash": "a1b2c3d4..."
  }
}
```

**Signature header** (if secret configured):
```
X-Webhook-Signature: sha256=<hmac_hex_digest>
```

---

## Rate Limiting

`POST /sign` and `POST /verify` are rate limited (default: 60 req/min per user).

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 55
X-RateLimit-Reset: 1707739200
```

Returns `429 Too Many Requests` when exceeded.

---

## File Requirements

| Extension | Type |
|-----------|------|
| `.vba` | VBA macro source |
| `.bas` | VBA module |
| `.cls` | VBA class module |
| `.frm` | VBA form |
| `.vbs` | VBScript |

Max size: **50 MB**. Empty files, path traversal attempts, and null bytes are rejected.

---

## Interactive Documentation

- **Swagger UI:** `http://localhost:8000/api/docs`
- **ReDoc:** `http://localhost:8000/api/redoc`
- **OpenAPI JSON:** `http://localhost:8000/api/openapi.json`
