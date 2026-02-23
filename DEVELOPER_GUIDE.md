# Macro Sign Service — Developer Guide

> Comprehensive API reference and integration guide for developers consuming Macro Sign Service from ServiceNow (SNOW) forms and CI/CD pipelines.

**Version:** 1.0.0
**Base URL:** `http://localhost:8000/api/v1`
**Interactive Docs:** [Swagger UI](http://localhost:8000/api/docs) | [ReDoc](http://localhost:8000/api/redoc) | [OpenAPI Spec](http://localhost:8000/api/openapi.json)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
  - [System Architecture](#system-architecture)
  - [SNOW Synchronous Flow](#snow-synchronous-flow)
  - [CI/CD Check-in Flow](#cicd-check-in-flow)
  - [Certificate Key Store](#certificate-key-store)
- [Getting Started](#getting-started)
- [Authentication](#authentication)
- [API Reference](#api-reference)
  - [ServiceNow Integration (SNOW)](#servicenow-integration-snow)
  - [Standard Signing (Async)](#standard-signing-async)
  - [Verification](#verification)
  - [Health](#health)
  - [Auth](#auth)
  - [Webhooks](#webhooks)
  - [Admin](#admin)
- [Integration Guide: ServiceNow](#integration-guide-servicenow)
  - [SNOW Business Rule](#snow-business-rule)
  - [SNOW Script Include](#snow-script-include)
  - [SNOW Flow Designer Action](#snow-flow-designer-action)
  - [Storing Signature in a SNOW Record](#storing-signature-in-a-snow-record)
- [Integration Guide: CI/CD Pipelines](#integration-guide-cicd-pipelines)
  - [GitHub Actions — check-in trigger](#github-actions--check-in-trigger)
  - [Azure DevOps Pipeline](#azure-devops-pipeline)
  - [Jenkins Pipeline](#jenkins-pipeline)
  - [Generic shell script](#generic-shell-script)
- [Error Handling](#error-handling)
- [Rate Limiting](#rate-limiting)
- [Webhook Events](#webhook-events)
- [File Requirements](#file-requirements)
- [Environment Configuration](#environment-configuration)
- [Running Tests](#running-tests)
- [Monitoring](#monitoring)

---

## Overview

Macro Sign Service provides **digital signing of Office VBA macros** using X.509 certificates. It is consumed by two categories of client:

| Consumer | Mode | Endpoint | Use case |
|----------|------|----------|----------|
| **ServiceNow GUI** | Synchronous | `POST /snow/sign` | A SNOW form, Business Rule, or Script Include submits a macro file and receives the signed content in a single HTTP response — no polling, no async. The SNOW record stores the returned `signature` and `signed_content_b64` fields. |
| **CI/CD pipeline** | Asynchronous | `POST /sign` → `GET /status/{job_id}` | A pipeline triggered on code check-in submits a macro for background signing, polls for the result, and attaches the signature to the build artifact. |

Both paths use the same signing engine, the same certificate key store, and the same audit trail.

---

## Architecture

### System Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CONSUMERS                                                               │
│                                                                          │
│  ┌──────────────────────┐     POST /api/v1/snow/sign                    │
│  │  ServiceNow (SNOW)   │ ──────────────────────────────────────┐       │
│  │  • Form UI           │  ◄── 200 OK                           │       │
│  │  • Business Rule     │       signed_content_b64              │       │
│  │  • Script Include    │       signature                       │       │
│  │  • Flow Designer     │       certificate_pem                 │       │
│  └──────────────────────┘                                       │       │
│                                                                  ▼       │
│  ┌──────────────────────┐     POST /api/v1/sign          ┌─────────────┐│
│  │  CI/CD Pipeline      │ ──────────────────────────────▶│  FastAPI    ││
│  │  • GitHub Actions    │  ◄── 202 Accepted (job_id)     │  API Server ││
│  │  • Azure DevOps      │                                │  :8000      ││
│  │  • Jenkins           │     GET /api/v1/status/{id}    └──────┬──────┘│
│  │  on: push / PR       │ ──────────────────────────────▶       │       │
│  └──────────────────────┘  ◄── 200 OK (signature)        ┌──────▼──────┐│
│                                                           │  Celery     ││
│  ┌──────────────────────┐                                │  Worker     ││
│  │  CLI / SDK           │ ──────────────────────────────▶│  (async)    ││
│  └──────────────────────┘                                └──────┬──────┘│
└─────────────────────────────────────────────────────────────────┼───────┘
                                                                  │
                   ┌──────────────────────────────────────────────┤
                   │                          │                   │
          ┌────────▼────────┐   ┌─────────────▼──────┐  ┌────────▼───────┐
          │  Certificate    │   │  PostgreSQL         │  │  Redis         │
          │  Key Store      │   │  • signing_jobs     │  │  Celery broker │
          │  • Local FS     │   │  • users / teams    │  │  result store  │
          │  • Vault        │   │  • audit_logs       │  └────────────────┘
          │  • AWS KMS      │   │  • api_keys         │
          │  • Azure KV     │   └────────────────────┘
          └─────────────────┘
```

---

### SNOW Synchronous Flow

The `/snow/sign` endpoint is purpose-built for ServiceNow. It accepts a file and returns the signed content in a **single synchronous HTTP 200 response** — no job IDs, no polling.

```
SNOW client
    │
    │  POST /api/v1/snow/sign
    │  Content-Type: multipart/form-data
    │  X-API-Key: mss_...
    │  file=<vba_bytes>
    │  requester_id=sys_u_abc123          ← SNOW user sys_id (audit)
    │  table=sys_script_include           ← SNOW table name (audit)
    │  domain=snow-test-domain            ← certificate to use
    │
    ▼
[ FileValidator ]
    Rejects: wrong extension, empty, >50 MB, path traversal
    ↓
[ CertificateStore.get_or_create_certificate("snow-test-domain") ]
    Returns existing cert or auto-provisions a self-signed test cert
    ↓
[ SigningEngine.sign(file_bytes, algorithm="sha256") ]
    RSA PKCS1v15 signature over file content
    ↓
[ AuditLog written to PostgreSQL ]
    action="snow.signing.completed", requester_id, table, IP
    ↓
    │
    │  HTTP 200 OK
    │  {
    │    "status": "signed",
    │    "signed_content_b64": "<base64 of original file>",
    │    "signature":           "<hex RSA signature>",
    │    "certificate_pem":     "<PEM public cert>",
    │    "certificate_subject": "CN=snow-test.macro-sign.local,...",
    │    "file_hash":           "<sha256 hex>",
    │    "signed_at":           "2026-02-23T10:00:00Z",
    │    "requester_id":        "sys_u_abc123"
    │  }
    ▼
SNOW form stores:
    u_macro_signature   ← response.signature
    u_signed_content    ← response.signed_content_b64
    u_cert_fingerprint  ← response.certificate_fingerprint
```

---

### CI/CD Check-in Flow

The `/sign` endpoint is designed for pipelines. It is **asynchronous** — the caller receives a `job_id` immediately and polls for the result.

```
Developer pushes code (git push / PR)
    │
    ▼
Pipeline trigger: on: push to main / on: pull_request
    │
    ▼
Step: Sign VBA macros
    │
    │  POST /api/v1/sign
    │  X-API-Key: mss_ci_pipeline_key
    │  file=report.vba
    │  algorithm=sha256
    │  webhook_url=https://ci.example.com/hooks/macro-sign   ← optional
    │
    ▼  202 Accepted  { "job_id": "abc-123", "status": "queued" }
    │
    ▼
Poll GET /api/v1/status/abc-123  every 2 seconds
    │
    ▼  until status == "completed"
    │  {
    │    "status": "completed",
    │    "signature": "3045022100...",
    │    "file_hash": "a1b2c3...",
    │    "certificate_fingerprint": "AB:CD:EF:..."
    │  }
    │
    ▼
Attach signature to build artifact / store in artifact repository
    │
    ▼
Pipeline passes — signed macro deployed
```

**Webhook alternative (event-driven):** Instead of polling, configure a `webhook_url`. The service posts to that URL when signing completes, eliminating the polling loop.

---

### Certificate Key Store

The key store is configurable via `CERT_STORE_BACKEND`. All backends implement the same interface including an idempotent `get_or_create_certificate()` method used by the SNOW endpoint to auto-provision the test-domain certificate on first use.

| Backend | Env value | Use case |
|---------|-----------|----------|
| Local filesystem | `local` | Development and testing — certificates stored in `./certs/` |
| HashiCorp Vault | `hashicorp_vault` | On-prem or private cloud — KV secrets engine v2 |
| AWS KMS / Secrets Manager | `aws_kms` | AWS-hosted workloads |
| Azure Key Vault | `azure_keyvault` | Azure-hosted workloads — DefaultAzureCredential or service principal |

On startup in non-production environments, the service auto-generates:
- `certs/default.pem` — general-purpose dev cert
- `certs/snow-test-domain.pem` — pre-provisioned SNOW test-domain cert

In production, provision certificates via the `/admin/profiles` API or directly in the key store backend.

---

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- A code-signing certificate (auto-generated in dev)

### Quick Start

```bash
git clone https://github.com/ojask7/macro-sign-service.git
cd macro-sign-service
cp .env.example .env
docker-compose up -d
curl http://localhost:8000/api/v1/health
```

### First Requests

```bash
# Register a user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"dev@example.com","username":"developer","password":"SecurePass123!","full_name":"Developer"}'

# Login
TOKEN=$(curl -sf -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"developer","password":"SecurePass123!"}' \
  | jq -r '.access_token')

# SNOW-style synchronous sign
curl -X POST http://localhost:8000/api/v1/snow/sign \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@my_macro.vba" \
  -F "requester_id=sys_u_test"

# Standard async sign
curl -X POST http://localhost:8000/api/v1/sign \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@my_macro.vba"
```

---

## Authentication

### JWT Bearer Tokens

Obtain via `/auth/login`. Include in requests:

```
Authorization: Bearer <access_token>
```

| Token | Lifetime | Purpose |
|-------|----------|---------|
| Access token | 30 min | API request auth |
| Refresh token | 7 days | Obtain new access tokens |

### API Keys

Better suited for CI/CD and SNOW integrations since they don't expire on short timers.

```
X-API-Key: mss_abc123...
```

Create via `POST /auth/api-keys`. The full key is shown **once at creation time only**.

### RBAC Roles

| Role | Allowed operations |
|------|--------------------|
| `admin` | All operations, user management, audit logs |
| `manager` | Team management, signing profiles, webhooks, analytics |
| `developer` | Sign macros (`/sign`, `/snow/sign`), verify, manage own API keys |
| `viewer` | Verify signatures, view own job status |

---

## API Reference

### ServiceNow Integration (SNOW)

#### `POST /api/v1/snow/sign` — Synchronous Sign

Signs a macro and returns the result synchronously. Designed for SNOW forms, Business Rules, and Script Includes that cannot poll for async results.

**Auth:** Required (developer+) | **Content-Type:** multipart/form-data

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `file` | Yes | — | Macro file (.vba .bas .cls .frm .vbs) |
| `algorithm` | No | `sha256` | `sha256` \| `sha384` \| `sha512` |
| `domain` | No | `snow-test-domain` | Certificate name in key store |
| `requester_id` | No | `null` | SNOW user sys_id (written to audit log) |
| `table` | No | `null` | SNOW table name (written to audit log) |

**Response: 200 OK**

```json
{
  "status": "signed",
  "original_filename": "report_macro.vba",
  "file_size": 2048,
  "signed_content_b64": "QXR0cmlidXRlIFZCX05hbWUg...",
  "signature": "3045022100abcdef1234...",
  "file_hash": "a1b2c3d4e5f6...",
  "certificate_fingerprint": "AB:CD:EF:01:23:45:...",
  "certificate_subject": "CN=snow-test.macro-sign.local,O=SNOW Test Domain,C=US",
  "certificate_pem": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n",
  "algorithm": "sha256",
  "signed_at": "2026-02-23T10:00:00Z",
  "requester_id": "sys_u_abc123",
  "domain": "snow-test-domain"
}
```

#### `POST /api/v1/snow/verify` — Verify SNOW Signature

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `file` | Yes | — | Original macro file |
| `signature` | Yes | — | Hex-encoded signature from sign response |
| `algorithm` | No | `sha256` | Must match algorithm used during signing |
| `domain` | No | `snow-test-domain` | Certificate domain used when signing |

**Response: 200 OK**

```json
{
  "is_valid": true,
  "certificate_subject": "CN=snow-test.macro-sign.local,...",
  "certificate_issuer": "CN=snow-test.macro-sign.local,...",
  "certificate_expiry": "2027-02-23T10:00:00Z",
  "message": "Signature is valid",
  "domain": "snow-test-domain"
}
```

#### `GET /api/v1/snow/certs` — List Key Store Certificates

**Response: 200 OK**

```json
{
  "certificates": ["default", "snow-test-domain", "production-2026"],
  "count": 3
}
```

---

### Standard Signing (Async)

#### `POST /api/v1/sign` — Submit Async Signing Job

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `file` | Yes | — | Macro file |
| `algorithm` | No | `sha256` | Hash algorithm |
| `profile` | No | `null` | Signing profile name |
| `webhook_url` | No | `null` | Callback URL on completion |

**Response: 202 Accepted**

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

#### `GET /api/v1/status/{job_id}` — Poll Job Status

When completed:

```json
{
  "job_id": "a1b2c3d4-...",
  "status": "completed",
  "file_hash": "a1b2c3d4...",
  "signature": "3045022100...",
  "certificate_fingerprint": "AB:CD:EF:...",
  "algorithm": "sha256",
  "started_at": "2026-02-23T10:00:01Z",
  "completed_at": "2026-02-23T10:00:02Z"
}
```

#### `GET /api/v1/sign/jobs` — List Jobs

Query params: `page` (default 1), `per_page` (default 20), `status_filter`.

---

### Verification

#### `POST /api/v1/verify`

**Form fields:** `file` (required), `signature` (required hex), `algorithm` (default `sha256`)

**Response: 200 OK** — `{ "is_valid": true/false, "message": "...", ... }`

---

### Health

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/health` | Full check — DB + Redis connectivity |
| `GET /api/v1/ready` | Kubernetes readiness probe |
| `GET /api/v1/live` | Kubernetes liveness probe |

---

### Auth

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Create user account |
| POST | `/auth/login` | Get access + refresh tokens |
| POST | `/auth/refresh` | Refresh access token |
| GET | `/auth/me` | Current user profile |
| POST | `/auth/api-keys` | Create API key |
| GET | `/auth/api-keys` | List API keys |
| DELETE | `/auth/api-keys/{id}` | Revoke API key |

---

### Webhooks

Create webhooks to receive push notifications instead of polling.

```json
POST /api/v1/webhooks
{
  "name": "CI Build Notifier",
  "url": "https://ci.example.com/hooks/macro-sign",
  "secret": "my-hmac-secret",
  "events": "signing.completed,signing.failed"
}
```

Payload delivered on event:

```json
{
  "event": "signing.completed",
  "timestamp": "2026-02-23T10:00:03Z",
  "data": {
    "job_id": "a1b2c3d4-...",
    "status": "completed",
    "signature": "3045022100...",
    "file_hash": "a1b2c3..."
  }
}
```

Verified via `X-Webhook-Signature: sha256=<hmac_hex>`. Retried up to 3 times on failure.

---

### Admin

All admin endpoints require `admin` or `manager` role.

| Method | Endpoint | Permission |
|--------|----------|------------|
| GET | `/admin/users` | `manage_users` |
| PATCH | `/admin/users/{id}` | `manage_users` |
| POST | `/admin/teams` | `manage_teams` |
| GET | `/admin/teams` | `manage_teams` |
| POST | `/admin/profiles` | `manage_profiles` |
| GET | `/admin/profiles` | authenticated |
| GET | `/admin/audit` | `view_audit` |
| GET | `/admin/dashboard/stats` | `view_analytics` |

---

## Integration Guide: ServiceNow

### SNOW Business Rule

Trigger macro signing automatically when a record containing a VBA attachment is inserted or updated.

```javascript
// Business Rule: "Sign VBA Attachment on Submit"
// Table: sys_script_include   When: before insert/update

(function executeRule(current, previous) {
    var SIGN_URL   = gs.getProperty('macro_sign.url', 'http://macro-sign-api:8000');
    var SIGN_KEY   = gs.getProperty('macro_sign.api_key');
    var DOMAIN     = gs.getProperty('macro_sign.domain', 'snow-test-domain');

    var attachment = new GlideSysAttachment();
    var attachData = attachment.getContent(current);  // base64 string

    if (!attachData) return;

    // Build multipart request via RESTMessageV2
    var req = new sn_ws.RESTMessageV2();
    req.setEndpoint(SIGN_URL + '/api/v1/snow/sign');
    req.setHttpMethod('POST');
    req.setRequestHeader('X-API-Key', SIGN_KEY);

    req.setRequestBodyFromBase64String(attachData);   // file bytes
    req.setRequestHeader('Content-Type', 'multipart/form-data');

    // Note: Use a MID Server Script for binary multipart in production.
    // Simplified version using JSON body for illustration:
    var body = {
        requester_id: current.sys_id.toString(),
        table:        current.getTableName(),
        domain:       DOMAIN,
        algorithm:    'sha256'
    };

    var resp = req.execute();
    if (resp.getStatusCode() == 200) {
        var data = JSON.parse(resp.getBody());
        current.u_macro_signature         = data.signature;
        current.u_cert_fingerprint        = data.certificate_fingerprint;
        current.u_macro_signed_at         = data.signed_at;
        current.u_macro_signing_status    = 'signed';
    } else {
        current.u_macro_signing_status = 'failed';
        gs.error('Macro Sign Service error: ' + resp.getBody());
    }
})(current, previous);
```

---

### SNOW Script Include

Reusable utility class callable from Business Rules, Flow Designer, and REST API scripts.

```javascript
// Script Include: MacroSignUtil   Client callable: false
var MacroSignUtil = Class.create();
MacroSignUtil.prototype = {
    initialize: function() {
        this.baseUrl = gs.getProperty('macro_sign.url', 'http://macro-sign-api:8000');
        this.apiKey  = gs.getProperty('macro_sign.api_key');
    },

    /**
     * Sign a macro file.
     * @param {string} fileContentB64 - Base64-encoded file bytes
     * @param {string} filename        - Original filename (e.g. "report.vba")
     * @param {string} requesterId     - SNOW sys_id of the requester
     * @param {string} table           - SNOW table name (for audit)
     * @returns {Object|null}          - Parsed sign response or null on error
     */
    signMacro: function(fileContentB64, filename, requesterId, table) {
        var req = new sn_ws.RESTMessageV2();
        req.setEndpoint(this.baseUrl + '/api/v1/snow/sign');
        req.setHttpMethod('POST');
        req.setRequestHeader('X-API-Key', this.apiKey);
        req.setQueryParameter('requester_id', requesterId);
        req.setQueryParameter('table', table || '');
        // File bytes and filename sent as multipart — handled via MID Server in prod

        var resp = req.execute();
        if (resp.getStatusCode() == 200) {
            return JSON.parse(resp.getBody());
        }
        gs.error('MacroSignUtil.signMacro failed [' + resp.getStatusCode() + ']: ' + resp.getBody());
        return null;
    },

    /**
     * Verify a previously signed macro.
     * @param {string} fileContentB64 - Base64-encoded original file bytes
     * @param {string} signature      - Hex-encoded signature from signMacro()
     * @param {string} filename       - Original filename
     * @returns {boolean} isValid
     */
    verifyMacro: function(fileContentB64, signature, filename) {
        var req = new sn_ws.RESTMessageV2();
        req.setEndpoint(this.baseUrl + '/api/v1/snow/verify');
        req.setHttpMethod('POST');
        req.setRequestHeader('X-API-Key', this.apiKey);
        req.setQueryParameter('signature', signature);

        var resp = req.execute();
        if (resp.getStatusCode() == 200) {
            return JSON.parse(resp.getBody()).is_valid === true;
        }
        return false;
    },

    /**
     * List available signing certificates.
     * @returns {Array<string>}
     */
    listCertificates: function() {
        var req = new sn_ws.RESTMessageV2();
        req.setEndpoint(this.baseUrl + '/api/v1/snow/certs');
        req.setHttpMethod('GET');
        req.setRequestHeader('X-API-Key', this.apiKey);

        var resp = req.execute();
        if (resp.getStatusCode() == 200) {
            return JSON.parse(resp.getBody()).certificates;
        }
        return [];
    },

    type: 'MacroSignUtil'
};
```

---

### SNOW Flow Designer Action

Create a custom **Flow Designer Action** for no-code signing in workflows:

1. **Action Input:** `file_sys_id` (Reference), `requester_id` (String)
2. **Script step:**

```javascript
(function execute(inputs, outputs) {
    var util = new MacroSignUtil();
    var attach = new GlideSysAttachment();
    var content = attach.getContentBase64(
        new GlideRecord('sys_attachment').initialize()  // use inputs.file_sys_id
    );

    var result = util.signMacro(content, 'macro.vba', inputs.requester_id, 'flow');

    if (result) {
        outputs.signature    = result.signature;
        outputs.file_hash    = result.file_hash;
        outputs.signed_at    = result.signed_at;
        outputs.status       = 'signed';
    } else {
        outputs.status = 'failed';
    }
})(inputs, outputs);
```

3. **Action Output:** `signature` (String), `file_hash` (String), `signed_at` (String), `status` (String)

---

### Storing Signature in a SNOW Record

After calling `/snow/sign`, store these fields on your target table:

| API response field | Recommended SNOW field | Type |
|-------------------|------------------------|------|
| `signature` | `u_macro_signature` | String (max 2048) |
| `certificate_fingerprint` | `u_cert_fingerprint` | String (max 100) |
| `file_hash` | `u_macro_file_hash` | String (max 100) |
| `signed_at` | `u_macro_signed_at` | Date/Time |
| `certificate_subject` | `u_cert_subject` | String (max 255) |
| `domain` | `u_signing_domain` | String (max 100) |

To verify later, retrieve the original file bytes (from the attachment) and the stored `u_macro_signature`, then call `/snow/verify`.

---

## Integration Guide: CI/CD Pipelines

### GitHub Actions — check-in trigger

Trigger macro signing on every push or pull request. Uses the **async** `/sign` endpoint with polling.

```yaml
# .github/workflows/sign-macros.yml
name: Sign VBA Macros

on:
  push:
    branches: [main, develop]
    paths: ['src/macros/**/*.vba', 'src/macros/**/*.bas']
  pull_request:
    paths: ['src/macros/**/*.vba', 'src/macros/**/*.bas']

jobs:
  sign:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Sign changed macro files
        env:
          MACRO_SIGN_URL: ${{ vars.MACRO_SIGN_URL }}
          MACRO_SIGN_API_KEY: ${{ secrets.MACRO_SIGN_API_KEY }}
        run: |
          set -euo pipefail

          sign_and_verify() {
            local file="$1"
            echo "Signing: $file"

            # Submit signing job
            local response
            response=$(curl -sf -X POST "$MACRO_SIGN_URL/api/v1/sign" \
              -H "X-API-Key: $MACRO_SIGN_API_KEY" \
              -F "file=@$file" \
              -F "algorithm=sha256")

            local job_id
            job_id=$(echo "$response" | jq -r '.job_id')
            echo "Job ID: $job_id"

            # Poll until completed (max 60 seconds)
            for i in $(seq 1 30); do
              local result
              result=$(curl -sf "$MACRO_SIGN_URL/api/v1/status/$job_id" \
                -H "X-API-Key: $MACRO_SIGN_API_KEY")
              local status
              status=$(echo "$result" | jq -r '.status')

              case "$status" in
                completed)
                  local sig
                  sig=$(echo "$result" | jq -r '.signature')
                  echo "Signed $file — signature: ${sig:0:16}..."
                  echo "$sig" > "${file}.sig"
                  return 0
                  ;;
                failed)
                  echo "ERROR: Signing failed for $file"
                  echo "$result" | jq '.error_message'
                  return 1
                  ;;
              esac
              sleep 2
            done

            echo "ERROR: Signing timed out for $file"
            return 1
          }

          # Sign all changed macro files
          git diff --name-only HEAD~1 HEAD -- '*.vba' '*.bas' '*.cls' | \
            while read -r file; do
              [ -f "$file" ] && sign_and_verify "$file"
            done

      - name: Upload signed artifacts
        uses: actions/upload-artifact@v4
        with:
          name: signed-macros
          path: |
            src/macros/**/*.vba
            src/macros/**/*.sig
```

#### Using the synchronous SNOW endpoint from GitHub Actions

If you prefer a simpler one-shot call (no polling), use the SNOW endpoint:

```yaml
      - name: Sign macro (synchronous)
        env:
          MACRO_SIGN_URL: ${{ vars.MACRO_SIGN_URL }}
          MACRO_SIGN_API_KEY: ${{ secrets.MACRO_SIGN_API_KEY }}
        run: |
          RESULT=$(curl -sf -X POST "$MACRO_SIGN_URL/api/v1/snow/sign" \
            -H "X-API-Key: $MACRO_SIGN_API_KEY" \
            -F "file=@src/macros/report.vba" \
            -F "requester_id=github-actions-${{ github.run_id }}")

          echo "$RESULT" | jq -r '.signature' > src/macros/report.vba.sig
          echo "Signed: $(echo $RESULT | jq -r '.file_hash')"
```

---

### Azure DevOps Pipeline

```yaml
# azure-pipelines.yml
trigger:
  branches:
    include: [main]
  paths:
    include: ['src/macros/*.vba']

pool:
  vmImage: ubuntu-latest

steps:
  - task: Bash@3
    displayName: Sign VBA macros
    env:
      MACRO_SIGN_URL: $(MACRO_SIGN_URL)
      MACRO_SIGN_API_KEY: $(MACRO_SIGN_API_KEY)
    inputs:
      targetType: inline
      script: |
        for FILE in src/macros/*.vba; do
          echo "Signing $FILE"

          RESULT=$(curl -sf -X POST "$MACRO_SIGN_URL/api/v1/snow/sign" \
            -H "X-API-Key: $MACRO_SIGN_API_KEY" \
            -F "file=@$FILE" \
            -F "requester_id=azdo-$(Build.BuildId)")

          echo $RESULT | jq -r '.signature' > "$FILE.sig"
          echo "Done: $FILE"
        done

  - task: PublishBuildArtifacts@1
    inputs:
      pathToPublish: src/macros
      artifactName: signed-macros
```

---

### Jenkins Pipeline

```groovy
pipeline {
    agent any
    environment {
        MACRO_SIGN_URL = credentials('macro-sign-url')
        MACRO_SIGN_API_KEY = credentials('macro-sign-api-key')
    }
    triggers {
        pollSCM('H/5 * * * *')  // or use webhook trigger
    }
    stages {
        stage('Sign Macros') {
            when {
                changeset 'src/macros/**/*.vba'
            }
            steps {
                sh '''
                    for FILE in src/macros/*.vba; do
                        RESULT=$(curl -sf -X POST "$MACRO_SIGN_URL/api/v1/snow/sign" \
                          -H "X-API-Key: $MACRO_SIGN_API_KEY" \
                          -F "file=@$FILE" \
                          -F "requester_id=jenkins-${BUILD_NUMBER}")
                        echo $RESULT | jq -r '.signature' > "$FILE.sig"
                    done
                '''
            }
        }
        stage('Archive') {
            steps {
                archiveArtifacts artifacts: 'src/macros/*.vba,src/macros/*.sig'
            }
        }
    }
}
```

---

### Generic Shell Script

For any CI/CD system, here is a complete shell helper:

```bash
#!/usr/bin/env bash
# macro-sign.sh — Sign a macro file and write the signature to <file>.sig
# Usage: ./macro-sign.sh <file.vba> [algorithm]
# Env:   MACRO_SIGN_URL, MACRO_SIGN_API_KEY
set -euo pipefail

FILE="${1:?Usage: $0 <file.vba> [algorithm]}"
ALGORITHM="${2:-sha256}"
API_URL="${MACRO_SIGN_URL:?Set MACRO_SIGN_URL}"
API_KEY="${MACRO_SIGN_API_KEY:?Set MACRO_SIGN_API_KEY}"

echo "[macro-sign] Signing $FILE with $ALGORITHM..."

RESULT=$(curl -sf -X POST "$API_URL/api/v1/snow/sign" \
  -H "X-API-Key: $API_KEY" \
  -F "file=@$FILE" \
  -F "algorithm=$ALGORITHM" \
  -F "requester_id=cicd-pipeline")

STATUS=$(echo "$RESULT" | jq -r '.status')
if [ "$STATUS" != "signed" ]; then
  echo "[macro-sign] ERROR: unexpected status '$STATUS'"
  echo "$RESULT" | jq .
  exit 1
fi

SIG=$(echo "$RESULT" | jq -r '.signature')
HASH=$(echo "$RESULT" | jq -r '.file_hash')
echo "$SIG" > "$FILE.sig"

echo "[macro-sign] Done"
echo "  File hash : $HASH"
echo "  Signature : ${SIG:0:24}..."
echo "  Saved to  : $FILE.sig"
```

---

## Error Handling

All errors return a consistent JSON body:

```json
{ "detail": "Human-readable error message" }
```

| Code | Meaning | Common causes |
|------|---------|---------------|
| `200` | OK | Successful synchronous sign/verify |
| `202` | Accepted | Async signing job queued |
| `400` | Bad Request | Invalid extension, empty file, file too large, bad signature hex |
| `401` | Unauthorized | Missing or expired token / API key |
| `403` | Forbidden | Insufficient RBAC permissions |
| `404` | Not Found | Job ID not found |
| `422` | Unprocessable Entity | Missing required form fields |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Unhandled exception |
| `503` | Service Unavailable | Certificate not available in key store |

---

## Rate Limiting

`POST /sign` and `POST /verify` are rate limited (default 60 req/min per user).

Response headers:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 55
X-RateLimit-Reset: 1707739200
```

`POST /snow/sign` and `POST /snow/verify` are not rate limited by default to accommodate synchronous SNOW form submissions.

---

## Webhook Events

| Event | Trigger |
|-------|---------|
| `signing.completed` | Async job finished successfully |
| `signing.failed` | Async job failed |

SNOW-specific audit events (`snow.signing.completed`, `snow.verification.completed`) are written to the database audit log but do **not** fire webhooks since the SNOW endpoint is synchronous.

---

## File Requirements

| Extension | Type |
|-----------|------|
| `.vba` | VBA macro source |
| `.bas` | VBA module |
| `.cls` | VBA class module |
| `.frm` | VBA form |
| `.vbs` | VBScript |

| Constraint | Limit |
|------------|-------|
| Max file size | 50 MB |
| Min file size | 1 byte |
| Path traversal (`../`, `\`) | Rejected |
| Null bytes in filename | Rejected |

Uploaded files are scanned for patterns like `Shell()`, `WScript.Shell`, `PowerShell`, `cmd.exe`. These generate warnings in the audit log but do **not** block signing.

---

## Environment Configuration

### SNOW-Specific Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CERT_STORE_BACKEND` | `local` | Key store backend: `local`, `hashicorp_vault`, `aws_kms`, `azure_keyvault` |
| `AZURE_KEYVAULT_URL` | — | Required when using Azure Key Vault backend |
| `AZURE_TENANT_ID` | — | Service-principal auth (optional — uses DefaultAzureCredential if unset) |
| `AZURE_CLIENT_ID` | — | Service-principal client ID |
| `AZURE_CLIENT_SECRET` | — | Service-principal client secret |

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | `development` \| `staging` \| `production` \| `testing` |
| `APP_SECRET_KEY` | — | App secret key (change in production) |
| `APP_PORT` | `8000` | API server port |
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection URL |
| `JWT_SECRET_KEY` | — | JWT signing secret |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `CELERY_BROKER_URL` | `redis://localhost:6379/1` | Celery broker |
| `SIGNING_DEFAULT_ALGORITHM` | `sha256` | Default hash algorithm |
| `SIGNING_MAX_FILE_SIZE_MB` | `50` | Max upload size |
| `RATE_LIMIT_ENABLED` | `true` | Enable rate limiting |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | Requests per minute per user |

---

## Running Tests

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# SNOW integration tests only
pytest tests/integration/test_snow_integration.py -v

# With coverage
pytest tests/ -v --cov=src --cov-report=term-missing
```

### Test Coverage

| Suite | File | Tests | Coverage areas |
|-------|------|-------|----------------|
| Signing Engine | `unit/test_signing_engine.py` | 27 | Sign, verify, algorithms, cert loading |
| File Validator | `unit/test_file_validator.py` | 14 | Extensions, size, path traversal, patterns |
| Certificate Store | `unit/test_certificate_store.py` | 8 | CRUD, rotation, metadata |
| JWT Handler | `unit/test_jwt_handler.py` | 10 | Tokens, API keys, hashing |
| Password | `unit/test_password.py` | 6 | Bcrypt hash/verify |
| Rate Limiter | `unit/test_rate_limiter.py` | 5 | Sliding window, headers |
| Settings | `unit/test_settings.py` | 9 | Config loading |
| **SNOW Integration** | `integration/test_snow_integration.py` | **46** | Full SNOW flow, tamper detection, keystore, rotation, round-trip |
| API Templates | `integration/test_api.py` | 4 | Structural templates |
| **Total** | | **129** | |

**SNOW test scenarios covered:**

| ID | Scenario |
|----|----------|
| SNOW-001/002/003 | Happy path — VBA / BAS / CLS files signed and returned |
| SNOW-004 | Algorithm variants — sha256, sha384, sha512 |
| SNOW-005 | Round-trip — sign then verify |
| SNOW-006 | Same-user flow — user who signed can verify |
| SNOW-007 | `requester_id` echoed in response |
| SNOW-008 | Unsupported extension rejected (400) |
| SNOW-009 | Oversized file rejected (400) |
| SNOW-010 | Unauthenticated request rejected (401) |
| SNOW-011 | Tampered file fails verification |
| SNOW-012 | Tampered signature fails verification |
| SNOW-013 | Key store listing |
| SNOW-014 | `get_or_create` auto-provisions missing cert |
| SNOW-015 | `get_or_create` returns existing cert without overwrite |
| SNOW-016 | Certificate rotation invalidates old signature |
| SNOW-017 | PEM cert in response is valid and verifiable |
| SNOW-018 | Multiple files signed sequentially (stateless) |

---

## Monitoring

### Prometheus Metrics

Available at `GET /metrics`:

| Metric | Description |
|--------|-------------|
| `http_requests_total` | Total requests by method / status / path |
| `http_request_duration_seconds` | Request latency histogram |
| `http_requests_in_progress` | In-flight requests |

### Grafana

Access at `http://localhost:3001` (default `admin`/`admin`). Pre-configured **Macro Sign Overview** dashboard.

### Health Endpoints

```bash
curl http://localhost:8000/api/v1/health   # DB + Redis check
curl http://localhost:8000/api/v1/ready    # Kubernetes readiness
curl http://localhost:8000/api/v1/live     # Kubernetes liveness
```

---

## Support

- **Interactive API Docs:** `http://localhost:8000/api/docs`
- **OpenAPI Spec:** `http://localhost:8000/api/openapi.json`
- **GitHub Issues:** [github.com/ojask7/macro-sign-service/issues](https://github.com/ojask7/macro-sign-service/issues)
