# Macro Sign Service — Demo Deck

### Automated VBA Macro Signing for Enterprise

**Presented to:** CISO | UK Macro Signing Team | Switzerland Team

**Date:** March 2026

---

## Agenda

1. The Problem — Current State & Pain Points
2. The Solution — Macro Sign Service
3. Value Stream & Benefits
4. Architecture Deep Dive
5. Live Demo
6. Next Steps — From PoC to Group Service

---

## 1. The Problem — Current State

### How macro signing works today (UK)

```
  Developer                  ServiceNow                UK Signing Team
  ─────────                  ──────────                ───────────────
      │                           │                           │
      ├── Upload .vba file ──────►│                           │
      │                           ├── Ticket created ────────►│
      │                           │                           │
      │                    ┌──────┤                           │
      │                    │ WAIT │   Manual review           │
      │                    │      │   Manual signing           │
      │                    │ Hours│   Manual verification      │
      │                    │  to  │   Manual upload back       │
      │                    │ Days │                           │
      │                    └──────┤                           │
      │                           │◄── Signed file returned ──┤
      │◄── Download signed file ──┤                           │
      │                           │                           │
```

### Key Bottlenecks

| Bottleneck | Impact |
|---|---|
| **Manual handoff** | Developer uploads → waits → team picks up → signs → returns |
| **Time delay** | Hours to days turnaround per signing request |
| **Human error** | Wrong certificate, missed files, copy-paste mistakes |
| **No audit trail** | Limited traceability of who signed what and when |
| **Scaling cost** | Dedicated team members tied up with repetitive tasks |
| **No CI/CD integration** | Macros checked into repos remain unsigned until manual process completes |
| **Single point of failure** | Key team members on leave = signing queue stalls |

### Switzerland — No Solution Exists

- CH team currently has **no macro signing capability**
- Unsigned macros are either blocked or accepted with elevated risk
- No standardised process, no tooling, no audit trail

---

## 2. The Solution — Macro Sign Service

### What is it?

An **enterprise-grade, automated macro signing service** that eliminates manual signing workflows entirely.

### Two Integration Patterns

| Pattern | Use Case | How It Works |
|---|---|---|
| **ServiceNow (Synchronous)** | Existing SNOW workflows | Submit macro → receive signed content back **instantly** (single HTTP call, 200 OK) |
| **CI/CD Pipeline (Async)** | GitHub Actions, Azure DevOps, Jenkins | Macro signed **automatically on every code check-in** (202 → poll → completed) |

### Before vs After

```
  BEFORE                                    AFTER
  ──────                                    ─────

  Upload to SNOW ──► Wait ──► Manual sign   Upload to SNOW ──► Signed instantly
  Hours to days turnaround                  Sub-second turnaround

  No CI/CD integration                      Auto-sign on git push

  Manual cert management                    Centralized cert store
                                            (Vault / AWS KMS / Azure Key Vault)

  Limited audit trail                       Full audit: user, IP, hash,
                                            cert fingerprint, timestamp

  Team bottleneck                           Zero human intervention

  UK only                                   Group-wide service
                                            (UK + CH + future entities)
```

---

## 3. Value Stream & Benefits

### Quantified Impact

| Metric | Before (Manual) | After (Automated) | Improvement |
|---|---|---|---|
| **Turnaround time** | Hours to days | Sub-second | ~99.9% faster |
| **Human effort per signing** | 15-30 min | 0 min | 100% eliminated |
| **Error rate** | Prone to manual mistakes | Deterministic, reproducible | Near-zero errors |
| **Audit completeness** | Partial / manual logs | Every operation fully logged | 100% traceability |
| **Availability** | Business hours, team dependent | 24/7 automated | Always-on |
| **CH coverage** | None | Full capability | New capability unlocked |

### Strategic Benefits

- **Security posture** — Every macro cryptographically signed with managed certificates; full audit trail satisfies compliance requirements
- **Developer velocity** — No more waiting; signing happens in CI/CD or instantly via SNOW
- **Operational cost** — Frees the signing team from repetitive manual work to focus on higher-value security tasks
- **Scalability** — Handles hundreds of signing requests per minute; no human bottleneck
- **Group standardization** — One service for UK and CH (and future entities); consistent policy, consistent tooling
- **Risk reduction** — Eliminates unsigned macros in CH; reduces human error in UK

---

## 4. Architecture Deep Dive

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CONSUMERS                                     │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  ┌───────────────┐  │
│  │  ServiceNow  │  │  CI/CD       │  │  CLI /   │  │  Admin        │  │
│  │  (SNOW)      │  │  Pipelines   │  │  SDK     │  │  Dashboard    │  │
│  │              │  │  GH Actions  │  │          │  │  (Next.js)    │  │
│  │  Sync Flow   │  │  Azure DevOps│  │  Local   │  │  :3000        │  │
│  └──────┬───────┘  │  Jenkins     │  │  dev     │  └───────┬───────┘  │
│         │          └──────┬───────┘  └────┬─────┘          │          │
└─────────┼─────────────────┼───────────────┼────────────────┼──────────┘
          │                 │               │                │
          ▼                 ▼               ▼                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      FastAPI  API  Server  (:8000)                      │
│                                                                         │
│  ┌─────────────┐  ┌────────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ /snow/sign  │  │ /sign      │  │ /auth/*  │  │ /admin/*         │  │
│  │ /snow/verify│  │ /status/   │  │ JWT +    │  │ Users, Teams,    │  │
│  │ /snow/certs │  │ /verify    │  │ API Keys │  │ Profiles, Audit  │  │
│  │ (Sync 200)  │  │ (Async 202)│  │ RBAC     │  │ Dashboard Stats  │  │
│  └─────────────┘  └─────┬──────┘  └──────────┘  └──────────────────┘  │
│                          │                                              │
│  ┌───────────────────────┼──────────────────────────────────────────┐  │
│  │              CORE ENGINE                                         │  │
│  │  ┌─────────────────┐  │  ┌────────────────────────────────────┐ │  │
│  │  │ Signing Engine   │  │  │ Certificate Store (Pluggable)      │ │  │
│  │  │ RSA / ECDSA      │  │  │                                    │ │  │
│  │  │ SHA-256/384/512  │  │  │  Local FS │ Vault │ AWS KMS │ Az  │ │  │
│  │  └─────────────────┘  │  └────────────────────────────────────┘ │  │
│  └───────────────────────┼─────────────────────────────────────────┘  │
└──────────────────────────┼────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Celery     │  │  PostgreSQL  │  │    Redis     │
│   Workers    │  │  (16)        │  │    (7)       │
│              │  │              │  │              │
│  sign_task   │  │  Users       │  │  Task broker │
│  verify_task │  │  Jobs        │  │  Results     │
│  webhook     │  │  Audit logs  │  │  Rate limits │
│              │  │  Certs meta  │  │  Cache       │
└──────────────┘  └──────────────┘  └──────────────┘
                           │
                    ┌──────┴──────┐
                    ▼             ▼
             ┌───────────┐ ┌───────────┐
             │Prometheus │ │ Grafana   │
             │  (:9090)  │ │  (:3001)  │
             │  Metrics  │ │ Dashboards│
             └───────────┘ └───────────┘
```

### ServiceNow Signing Flow (Detailed)

```
  SNOW Form / Business Rule
        │
        ├──► POST /api/v1/snow/sign
        │      ├─ file: .vba / .bas / .cls / .frm
        │      ├─ requester_id: SNOW sys_id
        │      └─ algorithm: sha256
        │
        ▼
  ┌─ File Validator ─┐
  │  Extension check │
  │  Size < 50 MB    │
  │  Pattern scan    │  (blocks Shell(), WScript, PowerShell, cmd.exe)
  └────────┬─────────┘
           ▼
  ┌─ Certificate Store ────────┐
  │  get_or_create_certificate │
  │  Auto-provisions domain    │
  │  cert if not exists        │
  └────────┬───────────────────┘
           ▼
  ┌─ Signing Engine ──────────┐
  │  SHA-256 hash of content  │
  │  RSA PKCS1v15 signature   │
  │  Certificate fingerprint  │
  └────────┬──────────────────┘
           ▼
  ┌─ Audit Log ───────────────┐
  │  user, IP, file hash,     │
  │  cert fingerprint, action │
  └────────┬──────────────────┘
           ▼
    HTTP 200 OK
    {
      "status": "signed",
      "signed_content_b64": "<base64>",
      "signature": "<hex>",
      "file_hash": "<hex>",
      "certificate_fingerprint": "AB:CD:...",
      "certificate_pem": "-----BEGIN...",
      "signed_at": "2026-03-02T10:00:00Z"
    }
```

### CI/CD Pipeline Signing Flow

```
  git push / PR merge
        │
        ├──► POST /api/v1/sign  (pipeline step)
        │
        ▼
    202 Accepted { job_id }
        │
        ├──► Celery worker picks up task
        │      ├─ Validate file
        │      ├─ Load certificate
        │      ├─ Sign macro (RSA/ECDSA)
        │      ├─ Store result in DB
        │      └─ Fire webhook (optional)
        │
        ▼
    Pipeline polls GET /status/{job_id}
        │
        ▼
    status: "completed"
    { signature, file_hash, certificate_fingerprint }
        │
        ▼
    Signed artifact stored / published
```

### Technology Stack

| Layer | Technology |
|---|---|
| **API** | Python 3.11+, FastAPI, Uvicorn |
| **Task Queue** | Celery + Redis broker |
| **Database** | PostgreSQL 16, SQLAlchemy (async) |
| **Crypto** | `cryptography` lib — RSA, ECDSA, X.509, SHA-256/384/512 |
| **Auth** | JWT (30 min) + API Keys + RBAC (4 roles) |
| **Dashboard** | Next.js 14, React 18, Tailwind CSS |
| **Cert Backends** | Local FS, HashiCorp Vault, AWS KMS, Azure Key Vault |
| **Monitoring** | Prometheus + Grafana |
| **Deployment** | Docker Compose (dev), Kubernetes + Helm (prod) |

### Security Controls

- Private keys never leave the vault / KMS — fetched at signing time only
- Full audit trail: user, IP, file hash, cert fingerprint, timestamp
- File validation: extension whitelist, size limit, dangerous pattern scanning
- RBAC: Admin, Manager, Developer, Viewer
- Webhook payloads signed with HMAC-SHA256
- Rate limiting: 60 req/min per user (configurable)
- API keys with `mss_` prefix for easy detection in secrets scanning

---

## 5. Live Demo

### What we will demonstrate

| # | Demo Item | What you will see |
|---|---|---|
| 1 | **Service startup** | `docker-compose up` — all services come online (API, workers, dashboard, DB, Redis, monitoring) |
| 2 | **Health check** | `curl /api/v1/health` — confirms DB + Redis connectivity |
| 3 | **SNOW synchronous signing** | POST a `.vba` file to `/snow/sign` — receive signed content back **instantly** (200 OK, sub-second) |
| 4 | **Signature verification** | POST the file + signature to `/snow/verify` — confirms `is_valid: true` |
| 5 | **CI/CD async signing** | POST to `/sign` → get `job_id` → poll `/status/{job_id}` → `completed` with signature |
| 6 | **Admin Dashboard** | Web UI showing signing jobs, audit logs, certificate management, user/team admin |
| 7 | **Audit trail** | Full log entry: who signed, when, what file hash, which certificate |
| 8 | **Certificate management** | List certs, view details, auto-provisioning of domain certificates |

### Demo Commands

```bash
# 1. Start the full stack
docker-compose up -d

# 2. Health check
curl http://localhost:8000/api/v1/health

# 3. Sign a macro via SNOW endpoint (synchronous — instant response)
curl -X POST http://localhost:8000/api/v1/snow/sign \
  -H "X-API-Key: mss_your_api_key" \
  -F "file=@sample_macro.vba" \
  -F "requester_id=demo_user_01" \
  -F "algorithm=sha256"

# 4. Verify the signature
curl -X POST http://localhost:8000/api/v1/snow/verify \
  -H "X-API-Key: mss_your_api_key" \
  -F "file=@sample_macro.vba" \
  -F "signature=<signature_from_step_3>"

# 5. Admin Dashboard
open http://localhost:3000
```

---

## 6. Next Steps — PoC to Group Service

### Current State by Entity

| Entity | Current State | With Macro Sign Service |
|---|---|---|
| **UK** | Manual SNOW workflow — team signs macros by hand | Automated signing via SNOW + CI/CD integration |
| **Switzerland (CH)** | **No solution** — macros unsigned or risk-accepted | Full signing capability — same service, same standards |
| **Future entities** | No standardization | Onboard to the same group service |

### Roadmap: PoC → Group Service

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │                                                                     │
  │   PHASE 1 — NOW                PHASE 2                 PHASE 3     │
  │   PoC / Demo                   Production Pilot        Group       │
  │                                                        Service     │
  │   ┌──────────────┐            ┌──────────────┐       ┌──────────┐ │
  │   │  Current     │            │  UK entity   │       │ Group-   │ │
  │   │  state       │     ──►    │  production  │  ──►  │ wide     │ │
  │   │              │            │  deployment  │       │ service  │ │
  │   │  Demo to     │            │              │       │          │ │
  │   │  CISO & teams│            │  CH entity   │       │ Managed  │ │
  │   │              │            │  onboarding  │       │ by Group │ │
  │   │  Validate    │            │              │       │ InfoSec  │ │
  │   │  approach    │            │  Integrate   │       │ & Group  │ │
  │   │              │            │  with Group  │       │ IAM      │ │
  │   └──────────────┘            │  IAM / IdP   │       │          │ │
  │                               └──────────────┘       └──────────┘ │
  │                                                                     │
  └─────────────────────────────────────────────────────────────────────┘
```

### Phase 1 — PoC / Demo (Current)

- Demonstrate end-to-end signing flow (SNOW + CI/CD)
- Validate architecture and security approach with CISO
- Gather feedback from UK signing team and CH stakeholders
- Confirm fit for both UK and CH requirements

### Phase 2 — Production Pilot

- Deploy to production infrastructure (Kubernetes)
- Integrate with **Group IAM** for centralised authentication (SSO / IdP)
- Integrate with enterprise certificate authority (CA-issued certs replacing self-signed)
- Connect to existing **ServiceNow** production instance
- Onboard UK team — migrate from manual workflow
- Onboard CH team — first-time macro signing capability
- Production monitoring via Prometheus + Grafana

### Phase 3 — Group Service

- Elevate from entity-level PoC to **official Group Service**
- Ownership transferred to / co-managed with **Group InfoSec** and **Group IAM**
- Centralised certificate lifecycle management
- HSM / PKCS#11 integration for hardware-backed keys
- Bulk signing API for high-volume pipelines
- SLA-backed availability and support model
- Onboard additional entities as needed

### Key Stakeholders for Next Phase

| Stakeholder | Role |
|---|---|
| **CISO** | Approve approach, sponsor Group Service elevation |
| **UK Macro Signing Team** | Primary users, validate workflow replacement |
| **CH Team** | New capability beneficiaries, validate requirements |
| **Group InfoSec** | Co-own the service, define certificate & signing policies |
| **Group IAM** | Integrate with centralised identity (SSO, API auth federation) |
| **Platform / Infra** | Kubernetes hosting, monitoring, SLA |

---

## Summary

| | Manual (Today) | Macro Sign Service |
|---|---|---|
| **Speed** | Hours to days | Sub-second |
| **Cost** | Dedicated team effort | Zero marginal cost per signing |
| **Coverage** | UK only | UK + CH + future entities |
| **Audit** | Partial | Complete, automated |
| **CI/CD** | Not integrated | Native integration |
| **Availability** | Business hours | 24/7 |
| **Risk** | Human error, unsigned macros (CH) | Deterministic, policy-enforced |

**One service. Two entities. Zero manual effort.**

---

*Macro Sign Service — Ojas K / Raghu Veerapandiyan*

*Repository: macro-sign-service*
