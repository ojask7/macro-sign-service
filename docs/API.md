# Macro Sign Service - API Documentation

## Base URL

```
http://localhost:8000/api/v1
```

## Authentication

The API supports two authentication methods:

### 1. JWT Bearer Token

Include the JWT token in the `Authorization` header:
```
Authorization: Bearer <your-jwt-token>
```

### 2. API Key

Include your API key in the `X-API-Key` header:
```
X-API-Key: mss_<your-api-key>
```

## Endpoints

### Health Check

#### `GET /api/v1/health`

Check the health status of the service.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "production",
  "timestamp": "2026-02-08T10:30:00Z",
  "checks": {
    "database": "healthy",
    "redis": "healthy"
  }
}
```

---

### Authentication

#### `POST /api/v1/auth/register`

Register a new user account.

**Request Body:**
```json
{
  "email": "user@example.com",
  "username": "johndoe",
  "password": "securepassword123",
  "full_name": "John Doe"
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "username": "johndoe",
  "role": "developer",
  "is_active": true,
  "created_at": "2026-02-08T10:30:00Z"
}
```

#### `POST /api/v1/auth/login`

Authenticate and receive JWT tokens.

**Request Body:**
```json
{
  "username": "johndoe",
  "password": "securepassword123"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

#### `GET /api/v1/auth/me`

Get current user profile. Requires authentication.

#### `POST /api/v1/auth/api-keys`

Create a new API key. Requires authentication.

**Request Body:**
```json
{
  "name": "CI/CD Pipeline Key",
  "expires_in_days": 90
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "name": "CI/CD Pipeline Key",
  "api_key": "mss_abc123...",
  "key_prefix": "mss_abc123",
  "is_active": true,
  "created_at": "2026-02-08T10:30:00Z",
  "expires_at": "2026-05-09T10:30:00Z"
}
```

> **Note:** The full API key is only shown once at creation time.

---

### Signing

#### `POST /api/v1/sign`

Submit a macro file for digital signing.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| file | file | Yes | The macro file (.vba, .bas, .cls, .frm, .vbs) |
| profile | string | No | Signing profile name |
| algorithm | string | No | Hash algorithm (sha256, sha384, sha512) |
| webhook_url | string | No | Webhook URL for completion notification |

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/sign \
  -H "X-API-Key: mss_your_key" \
  -F "file=@my_macro.vba" \
  -F "algorithm=sha256"
```

**Response:** `202 Accepted`
```json
{
  "job_id": "abc-123-def",
  "status": "queued",
  "original_filename": "my_macro.vba",
  "file_size": 1024,
  "algorithm": "sha256",
  "created_at": "2026-02-08T10:30:00Z"
}
```

#### `GET /api/v1/status/{job_id}`

Check the status of a signing job.

**Response:**
```json
{
  "job_id": "abc-123-def",
  "status": "completed",
  "original_filename": "my_macro.vba",
  "file_size": 1024,
  "file_hash": "a1b2c3d4...",
  "signature": "deadbeef...",
  "certificate_fingerprint": "f0e1d2c3...",
  "algorithm": "sha256",
  "created_at": "2026-02-08T10:30:00Z",
  "started_at": "2026-02-08T10:30:01Z",
  "completed_at": "2026-02-08T10:30:03Z"
}
```

#### `POST /api/v1/verify`

Verify a signed macro file.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| file | file | Yes | The macro file to verify |
| signature | string | Yes | Hex-encoded digital signature |
| algorithm | string | No | Hash algorithm used (default: sha256) |

**Response:**
```json
{
  "is_valid": true,
  "certificate_subject": "CN=Macro Sign Prod, O=Company Inc",
  "certificate_issuer": "CN=Company CA",
  "certificate_expiry": "2027-01-15T00:00:00Z",
  "message": "Signature is valid"
}
```

---

### Admin Endpoints

All admin endpoints require appropriate RBAC permissions.

#### `GET /api/v1/admin/users` - List all users (admin)
#### `PATCH /api/v1/admin/users/{user_id}` - Update user (admin)
#### `POST /api/v1/admin/teams` - Create team (manager+)
#### `GET /api/v1/admin/teams` - List teams (manager+)
#### `POST /api/v1/admin/profiles` - Create signing profile (manager+)
#### `GET /api/v1/admin/profiles` - List signing profiles
#### `GET /api/v1/admin/audit` - View audit logs
#### `GET /api/v1/admin/dashboard/stats` - Dashboard statistics

---

### Webhooks

#### `POST /api/v1/webhooks` - Create webhook
#### `GET /api/v1/webhooks` - List webhooks
#### `PATCH /api/v1/webhooks/{id}` - Update webhook
#### `DELETE /api/v1/webhooks/{id}` - Delete webhook

**Webhook Payload:**
```json
{
  "job_id": "abc-123-def",
  "status": "completed",
  "signature": "deadbeef...",
  "file_hash": "a1b2c3d4..."
}
```

**Webhook Headers:**
```
Content-Type: application/json
X-Macro-Sign-Event: signing.completed
X-Macro-Sign-Signature: sha256=<hmac-signature>
```

---

## Rate Limiting

API responses include rate limit headers:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 59
X-RateLimit-Reset: 1707392400
```

When rate limited, the API returns `429 Too Many Requests`.

## Error Responses

All errors follow a consistent format:

```json
{
  "error": "Error type",
  "detail": "Detailed error message",
  "status_code": 400
}
```

## Interactive Documentation

- **Swagger UI:** `http://localhost:8000/api/docs`
- **ReDoc:** `http://localhost:8000/api/redoc`
- **OpenAPI JSON:** `http://localhost:8000/api/openapi.json`
