# Macro Sign Service

> Enterprise-grade macro signing service that automates digital signing of Office macros (VBA) for speed, security, and compliance.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

---

## What is this?

Organizations that use Office macros face a constant challenge: **unsigned macros are a security risk**, but manually signing them slows down development. Macro Sign Service solves this by providing a centralized, automated signing service that integrates into your existing **CI/CD pipelines** and **ServiceNow (SNOW) workflows**.

### Key Features

- **Synchronous SNOW signing** — ServiceNow forms submit a macro and receive the signed content back in a single HTTP call (no polling)
- **Async CI/CD signing** — Pipeline check-in events trigger signing jobs processed by Celery workers
- **Certificate Management** — Integrates with Azure Key Vault, AWS KMS, HashiCorp Vault, and local filesystem
- **Audit Trail** — Every signing operation is logged with user, IP, file hash, and certificate fingerprint
- **Role-Based Access Control** — Granular permissions for admins, managers, developers, and viewers
- **Admin Dashboard** — Web UI for managing certificates, viewing signing history, and monitoring usage
- **CLI Tool** — Sign macros locally during development

---

## Architecture

The service supports two distinct consumer patterns: **ServiceNow GUI** (synchronous, returns signed content directly) and **CI/CD pipelines** (asynchronous, job-based).

### VBA Project Signing (Office Macro Files)

Office files (.xlsm, .docm, .pptm) require **Microsoft SignTool + Office SIP DLLs** to produce valid VBA project signatures visible in Excel/Word (Alt+F11 → Tools → Digital Signature). This only works on Windows with Office installed.

The service uses a **Windows Signing Agent** architecture: the Linux API delegates signing to a lightweight Flask service running on a Windows host.

```
                  WSL / Docker (Linux)                    Windows Host (physical or VM)
        ┌─────────────────────────────────┐         ┌──────────────────────────────────┐
        │  FastAPI API   (:8000)          │         │  Windows Signing Agent  (:5100)  │
        │  ┌───────────────────────────┐  │  HTTP   │  ┌────────────────────────────┐  │
User ──▶│  │ POST /snow/sign-vba      │──┼────────▶│  │ POST /sign               │  │
        │  │                           │  │         │  │   signtool.exe + SIP DLLs │  │
        │  │ VBASigningEngine          │  │◀────────│  │   msosip.dll              │  │
        │  └───────────────────────────┘  │  signed │  └────────────────────────────┘  │
        │  Celery Workers                 │  file   │  Microsoft Office (installed)    │
        │  Redis                          │         │  Windows SDK (signtool.exe)      │
        └─────────────────────────────────┘         └──────────────────────────────────┘
```

**Signing priority inside `VBASigningEngine`:**
1. **Local signtool** — if running natively on Windows with Office + SDK
2. **Remote Windows Signing Agent** — HTTP delegation to `SIGNING_WINDOWS_AGENT_URL`
3. **Fallback** — returns unsigned file with `signing_method: "unsigned-requires-windows"`

### SNOW Synchronous Flow

```
SNOW Form  ──[POST /api/v1/snow/sign  file + requester_id]──▶  API
                                                                  │ validate
                                                                  │ get_or_create_certificate("snow-test-domain")
                                                                  │ sign (RSA SHA-256)
           ◄──[200 OK  signed_content_b64 + signature + cert]──  │
SNOW stores signature in record field
SNOW later  ──[POST /api/v1/snow/verify  file + signature]──▶  API
           ◄──[200 OK  is_valid: true/false]──────────────────   │
```

### SNOW VBA Signing Flow (Office Files)

```
SNOW Form  ──[POST /api/v1/snow/sign-vba  .xlsm/.docm file]──▶  API
                                                                     │ validate extension
                                                                     │ get_or_create_certificate (PFX)
                                                                     │ VBASigningEngine.sign_file()
                                                                     │   └──▶ Windows Agent (HTTP)
                                                                     │         └──▶ signtool + Office SIP
           ◄──[200 OK  signed_file_b64 + certificate + method]────  │
User opens signed file in Excel → Alt+F11 → Tools → Digital Signature → Certificate visible ✓
```

### CI/CD Check-in Flow

```
Developer pushes code
       │
       ▼
  Pipeline trigger (on: push / pull_request)
       │
       ▼
  POST /api/v1/sign  ──▶  202 Accepted  { job_id }
       │
       ▼
  Poll GET /api/v1/status/{job_id}  until  status == "completed"
       │
       ▼
  Retrieve signature + file_hash from response
       │
       ▼
  Store / publish signed artifact
```

---

## Getting Started

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local development)
- A code-signing certificate (self-signed generated automatically for dev, CA-issued for production)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/ojask7/macro-sign-service.git
cd macro-sign-service

# Copy environment config
cp .env.example .env

# Start all services
docker-compose up -d

# Verify it's running
curl http://localhost:8000/api/v1/health
```

### Running Services

Once `docker-compose up -d` completes, the following services are available:

| Service | URL | Description |
|---------|-----|-------------|
| **API** | [http://localhost:8000](http://localhost:8000) | REST API server |
| **Swagger UI** | [http://localhost:8000/api/docs](http://localhost:8000/api/docs) | Interactive API documentation |
| **Dashboard** | [http://localhost:3000](http://localhost:3000) | Admin web UI (certificates, audit logs, stats) |
| **SNOW Mock** | [http://localhost:3000/snow-mock](http://localhost:3000/snow-mock) | ServiceNow mock signing form for demos |
| **Grafana** | [http://localhost:3001](http://localhost:3001) | Monitoring dashboards (admin / admin) |
| **Prometheus** | [http://localhost:9090](http://localhost:9090) | Metrics collection UI |
| **Windows Agent** | `http://<windows-host>:5100` | VBA signing agent (runs on Windows, not Docker) |

### Windows Signing Agent Setup

The Windows Signing Agent is required for VBA project signing (so certificates appear in Excel/Word's Digital Signature dialog). It runs on your **Windows host** (not in Docker).

**Prerequisites on Windows:**
- Microsoft Office installed (provides `msosip.dll` SIP DLLs)
- Windows SDK installed (provides `signtool.exe`) — install via Visual Studio Installer → Individual Components → "Windows SDK Signing Tools"
- Python 3.9+ with Flask: `pip install flask`

**Start the agent:**
```powershell
python scripts/windows_signing_agent.py --port 5100
```

**Verify it's ready:**
```powershell
curl http://localhost:5100/health
# Should return: {"signing_ready": true, "signtool_found": true, "office_sip_found": true}
```

**Connect from WSL/Docker — add to your `.env`:**
```bash
SIGNING_WINDOWS_AGENT_URL=http://host.docker.internal:5100
```

> **Note:** `host.docker.internal` resolves to the Windows host from inside Docker on WSL. If that doesn't work, use your Windows host LAN IP (`ipconfig` → IPv4 Address).

### ServiceNow Mock Demo

The built-in ServiceNow mock page at **[http://localhost:3000/snow-mock](http://localhost:3000/snow-mock)** provides a realistic SNOW-styled interface for demonstrating the signing workflow without a live ServiceNow instance.

**How to use it:**

1. Open [http://localhost:3000/snow-mock](http://localhost:3000/snow-mock) in your browser
2. Log in with your MSS credentials (or register via the API)
3. Upload a VBA macro file (`.vba`, `.bas`, `.cls`, `.frm`, `.vbs` — max 50 MB)
4. Select a hash algorithm (SHA-256 / SHA-384 / SHA-512) and signing domain
5. Click **Sign** — the signed content is returned immediately (synchronous flow)
6. Download the signed file and review the signing details (hash, signature, certificate info)

The mock form calls the real `/api/v1/snow/sign` endpoint, so it exercises the full signing pipeline.

### Local Development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
make test
```

On startup the service automatically generates:
- `certs/default.pem` — general-purpose dev signing certificate
- `certs/snow-test-domain.pem` — pre-provisioned certificate for SNOW test-domain signing

---

## API Reference

### ServiceNow Integration (Synchronous)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/snow/sign` | Sign a macro and return signed content **immediately** (200 OK, no polling) |
| POST | `/api/v1/snow/sign-vba` | Sign an Office macro file (.xlsm/.docm/.pptm) via Windows SignTool + SIP |
| POST | `/api/v1/snow/verify` | Verify a previously signed macro |
| GET | `/api/v1/snow/certs` | List available certificates in the key store |
| GET | `/api/v1/snow/certs/{name}` | Get certificate details for a domain |
| GET | `/api/v1/snow/certs/{name}/proof` | Get certificate proof with code-signing validation |
| GET | `/api/v1/snow/certs/{name}/pfx` | Download certificate as PFX/PKCS#12 for Windows import |

### Standard Signing (Asynchronous)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/sign` | Submit a macro for async signing (202 Accepted + job_id) |
| GET | `/api/v1/status/{job_id}` | Poll signing job status |
| POST | `/api/v1/verify` | Verify a signed macro |
| GET | `/api/v1/health` | Health check |

### SNOW Signing Example

```bash
# Sign a macro — response returns signed content immediately
curl -X POST http://localhost:8000/api/v1/snow/sign \
  -H "X-API-Key: mss_your_api_key" \
  -F "file=@report_macro.vba" \
  -F "requester_id=sys_u_abc123" \
  -F "algorithm=sha256"
```

**Response (200 OK):**
```json
{
  "status": "signed",
  "original_filename": "report_macro.vba",
  "file_size": 1024,
  "signed_content_b64": "QXR0cmlidXRlIFZCX05hbWUg...",
  "signature": "3045022100abcdef...",
  "file_hash": "a1b2c3d4...",
  "certificate_fingerprint": "AB:CD:EF:...",
  "certificate_subject": "CN=snow-test.macro-sign.local,O=SNOW Test Domain,C=US",
  "certificate_pem": "-----BEGIN CERTIFICATE-----\n...",
  "algorithm": "sha256",
  "signed_at": "2026-02-23T10:00:00Z",
  "requester_id": "sys_u_abc123",
  "domain": "snow-test-domain"
}
```

### CI/CD Pipeline Example (GitHub Actions)

```yaml
- name: Sign VBA macro on check-in
  env:
    MACRO_SIGN_URL: ${{ vars.MACRO_SIGN_URL }}
    MACRO_SIGN_API_KEY: ${{ secrets.MACRO_SIGN_API_KEY }}
  run: |
    # Submit signing job
    JOB_ID=$(curl -sf -X POST "$MACRO_SIGN_URL/api/v1/sign" \
      -H "X-API-Key: $MACRO_SIGN_API_KEY" \
      -F "file=@src/macros/report.vba" \
      | jq -r '.job_id')

    # Poll until complete
    for i in $(seq 1 30); do
      RESULT=$(curl -sf "$MACRO_SIGN_URL/api/v1/status/$JOB_ID" \
        -H "X-API-Key: $MACRO_SIGN_API_KEY")
      STATUS=$(echo "$RESULT" | jq -r '.status')
      [ "$STATUS" = "completed" ] && break
      [ "$STATUS" = "failed" ] && exit 1
      sleep 2
    done

    echo "Signature: $(echo $RESULT | jq -r '.signature')"
```

---

## Project Structure

```
macro-sign-service/
├── .github/workflows/      # CI/CD pipelines
├── src/
│   ├── api/
│   │   ├── snow.py         # ServiceNow endpoints (sign, sign-vba, verify, certs)
│   │   ├── signing.py      # Async signing endpoints (sign/status/verify)
│   │   ├── auth.py         # Authentication & API key management
│   │   ├── admin.py        # Admin: users, teams, profiles, audit
│   │   ├── health.py       # Health / readiness / liveness probes
│   │   └── webhooks.py     # Webhook management
│   ├── core/
│   │   ├── signing_engine.py     # RSA/ECDSA signing & verification
│   │   ├── vba_signing.py        # VBA project signing (SignTool + Windows Agent)
│   │   └── certificate_store.py  # Local / Vault / AWS / Azure backends
│   ├── auth/               # JWT, API keys, RBAC
│   ├── models/             # SQLAlchemy ORM + Pydantic schemas
│   ├── queue/              # Celery tasks (auto-routes Office files to VBA signing)
│   ├── utils/              # File validator, rate limiter
│   └── config/             # Settings (includes SIGNING_WINDOWS_AGENT_URL)
├── scripts/
│   ├── windows_signing_agent.py  # Flask agent for Windows VM (signtool + SIP)
│   ├── sign-vba.ps1              # PowerShell script for local signtool signing
│   └── sign-vba.bat              # Batch wrapper
├── tests/
│   ├── unit/
│   │   └── test_vba_signing.py        # 21 unit tests for VBA signing engine
│   ├── e2e/
│   │   └── test_vba_signing_e2e.py    # 7 E2E tests for VBA signing API
│   └── integration/
│       └── test_snow_integration.py   # 46 SNOW end-to-end tests
├── dashboard/              # Admin web UI (Next.js)
│   └── app/snow-mock/      # ServiceNow mock signing form
├── cli/                    # CLI tool (sign, sign-vba, verify, cert-info)
├── docs/                   # API.md, DEPLOYMENT.md
├── deploy/                 # Docker & Helm charts
├── docker-compose.yml
├── Makefile
└── DEVELOPER_GUIDE.md
```

---

## Testing

### Run Unit Tests

```bash
python -m pytest tests/unit/test_vba_signing.py -v
```

**21 tests** covering the VBA signing engine — runs on any platform (Linux/Mac/Windows), no Windows agent needed:

| Suite | Tests | What it covers |
|-------|-------|----------------|
| `TestCreateCodeSigningPfx` | 5 | PFX generation, Code Signing EKU, custom CN, password, key size |
| `TestPemToPfx` | 2 | PEM cert+key → PFX conversion with and without password |
| `TestVBASigningEngineInit` | 4 | Engine init from PFX, PEM, error handling for missing certs |
| `TestSignFileFallback` | 2 | Linux fallback returns `unsigned-requires-windows`, missing PFX raises error |
| `TestSignViaAgent` | 3 | Mocked HTTP agent delegation, unhealthy agent fallback, unreachable agent fallback |
| `TestGetCertificateDetails` | 4 | Certificate fields, code signing flag, fingerprint format, EKU extension |
| `TestVBASigningResult` | 1 | Result dataclass `to_dict()` output |

### Run E2E Tests

Requires the full stack running (Docker + Windows Signing Agent):

```bash
MACRO_SIGN_URL=http://localhost:8000 \
MACRO_SIGN_API_KEY=<your-key> \
python -m pytest tests/e2e/test_vba_signing_e2e.py -v
```

| TC | Test | Validates |
|----|------|-----------|
| TC-01 | `test_sign_xlsm_returns_signed_file` | .xlsm signing returns status=signed, valid base64, cert fingerprint & subject |
| TC-02 | `test_signing_method_is_windows_based` | signing_method is `signtool-office-sip`, `windows-agent-signtool-sip`, or `unsigned-requires-windows` |
| TC-03 | `test_sign_docm` | .docm signing works, preserves original_filename |
| TC-04 | `test_cert_proof_shows_code_signing` | `/certs/{domain}/proof` returns is_code_signing=true |
| TC-05 | `test_pfx_download` | `/certs/{domain}/pfx` returns valid application/x-pkcs12 |
| TC-06 | *(implicit in TC-02)* | Unsigned fallback when no Windows agent configured |
| TC-07 | `test_reject_non_office_file` | Non-Office files (.vba) return 400 error |

### Manual Validation (Demo Scenario)

This is the test that failed in the demo — use this to verify the fix:

1. Start Docker services: `docker-compose up -d`
2. Start Windows Signing Agent on your Windows host:
   ```powershell
   pip install flask
   python scripts/windows_signing_agent.py --port 5100
   ```
3. Set `SIGNING_WINDOWS_AGENT_URL=http://host.docker.internal:5100` in `.env`, restart API
4. Upload an .xlsm file via SNOW Mock ([http://localhost:3000/snow-mock](http://localhost:3000/snow-mock)) or API:
   ```bash
   curl -X POST http://localhost:8000/api/v1/snow/sign-vba \
     -H "X-API-Key: <key>" \
     -F "file=@report.xlsm" \
     -F "domain=snow-test-domain"
   ```
5. Download the signed file (base64 decode `signed_file_b64` from response)
6. Open in Excel → **Alt+F11** → **Tools** → **Digital Signature**
7. **Certificate should be visible** with subject and thumbprint matching the API response

### Test Report Summary

| Area | Status | Details |
|------|--------|---------|
| PFX certificate generation | PASS | Code Signing EKU (OID 1.3.6.1.5.5.7.3.3) correctly embedded |
| VBA signing engine init | PASS | Initializes from PFX, PEM, or auto-generates |
| Linux fallback (no agent) | PASS | Returns `unsigned-requires-windows` — does not fake a signature |
| Windows agent delegation | PASS (mocked) | Correct HTTP payload sent, signed file returned |
| Agent health check | PASS (mocked) | Unhealthy/unreachable agent triggers graceful fallback |
| Certificate proof endpoint | PASS | Confirms is_code_signing=true, PFX available |
| Office file rejection | PASS | Non-Office extensions (.vba, .txt) rejected with 400 |
| osslsigncode removed | PASS | No longer in Dockerfiles or signing engine |
| Set-AuthenticodeSignature removed | PASS | PowerShell script uses signtool.exe only |

---

## Security

- All signing operations are logged with full audit trails (user, IP, file hash, cert fingerprint)
- Private keys are fetched from secure vaults at runtime — never written to application logs
- API authentication via JWT bearer tokens and API keys with RBAC
- Webhook payloads signed with HMAC-SHA256
- File uploads scanned for dangerous shell patterns before signing
- Regular security scanning via GitHub Advanced Security

---

## Roadmap

- [x] Core signing engine (RSA/ECDSA, SHA-256/384/512)
- [x] REST API with JWT + API key authentication
- [x] Async signing via Celery workers
- [x] Certificate store integration (Local, HashiCorp Vault, AWS KMS, Azure Key Vault)
- [x] ServiceNow synchronous signing integration (`/snow/sign`)
- [x] CI/CD pipeline integration (GitHub Actions, Azure DevOps, Jenkins)
- [x] Admin dashboard (Next.js)
- [x] CLI tool
- [x] Kubernetes deployment (Helm charts)
- [x] VBA project signing via Windows SignTool + Office SIP DLLs
- [x] Windows Signing Agent (HTTP delegation for Linux→Windows signing)
- [x] Certificate proof & PFX download endpoints
- [ ] Bulk signing API (batch multiple files in one request)
- [ ] Distributed rate limiting (Redis-backed)
- [ ] Certificate expiry alerts
- [ ] HSM / PKCS#11 support

---

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes
4. Push to the branch and open a Pull Request

---

## License

Apache License 2.0 — see the [LICENSE](LICENSE) file for details.

---

**Ojas K / Raghu Veerapandiyan** — [@ojask7](https://github.com/ojask7)

Project: [https://github.com/ojask7/macro-sign-service](https://github.com/ojask7/macro-sign-service)
