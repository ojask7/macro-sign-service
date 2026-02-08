# 🔐 Macro Sign Service

> Enterprise-grade macro signing service that automates digital signing of Office macros (VBA) for speed, security, and compliance.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

---

## 🧐 What is this?

Organizations that use Office macros face a constant challenge: **unsigned macros are a security risk**, but manually signing them slows down development. Macro Sign Service solves this by providing a centralized, automated signing service that integrates into your existing CI/CD pipelines.

### Key Features

- **Automated Macro Signing** — Submit VBA macro files via API and receive signed files back in seconds
- **Certificate Management** — Integrates with Azure Key Vault, AWS KMS, and HashiCorp Vault for secure certificate storage
- **CI/CD Integration** — GitHub Actions, Azure DevOps, and Jenkins plugins for seamless pipeline integration
- **Audit Trail** — Full logging of every signing operation for compliance and forensics
- **Role-Based Access Control** — Teams and users with granular permissions
- **Admin Dashboard** — Web UI for managing certificates, viewing signing history, and monitoring usage
- **CLI Tool** — Sign macros locally during development

---

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  CI/CD      │     │   Macro Sign     │     │  Certificate    │
│  Pipeline / │────▶│   Service API    │────▶│  Store          │
│  CLI / UI   │     │  (FastAPI)       │     │  (Vault/KMS)    │
└─────────────┘     └───────┬──────────┘     └─────────────────┘
                            │
                    ┌───────▼──────────┐
                    │   Task Queue     │
                    │   (Celery/Redis) │
                    └───────┬──────────┘
                            │
                    ┌───────▼──────────┐
                    │   PostgreSQL     │
                    │   (Audit Logs)   │
                    └──────────────────┘
```

---

## 🚀 Getting Started

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local development)
- A code-signing certificate (self-signed for dev, CA-issued for production)

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

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Run the service
uvicorn src.main:app --reload --port 8000

# Run tests
make test
```

---

## 📡 API Reference

| Method | Endpoint                  | Description                    |
|--------|---------------------------|--------------------------------|
| POST   | `/api/v1/sign`            | Submit a macro file for signing |
| GET    | `/api/v1/status/{job_id}` | Check signing job status        |
| POST   | `/api/v1/verify`          | Verify a signed macro           |
| GET    | `/api/v1/health`          | Health check                    |

### Example: Sign a Macro

```bash
curl -X POST http://localhost:8000/api/v1/sign \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "file=@my_macro.vba" \
  -F "profile=production"
```

**Response:**
```json
{
  "job_id": "abc-123-def",
  "status": "queued",
  "message": "Macro submitted for signing"
}
```

---

## 📁 Project Structure

```
macro-sign-service/
├── .github/workflows/      # CI/CD pipelines
├── src/
│   ├── api/                # API routes & controllers
│   ├── core/               # Signing engine & business logic
│   ├── auth/               # Authentication & authorization
│   ├── models/             # Database models
│   ├── queue/              # Async job processing
│   ├── utils/              # Helpers & utilities
│   └── config/             # Configuration management
├── tests/                  # Unit, integration & e2e tests
├── dashboard/              # Admin web UI
├── cli/                    # CLI tool
├── docs/                   # Documentation
├── deploy/                 # Docker & Helm charts
├── docker-compose.yml
├── Makefile
├── README.md
└── LICENSE
```

---

## 🔒 Security

- All signing operations are logged with full audit trails
- Certificates are never stored on disk — fetched from secure vaults at runtime
- API authentication via JWT/API keys with RBAC
- Supports mTLS for service-to-service communication
- Regular security scanning via GitHub Advanced Security

---

## 🛣️ Roadmap

- [x] Project setup & initial architecture
- [ ] Core signing engine
- [ ] REST API with authentication
- [ ] Certificate store integration (Vault/KMS)
- [ ] CI/CD plugins (GitHub Actions, Azure DevOps)
- [ ] Admin dashboard
- [ ] CLI tool
- [ ] Kubernetes deployment (Helm charts)
- [ ] Multi-tenant support

See [PLAN.md](PLAN.md) for the detailed project plan.

---

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines before submitting a PR.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the Apache License 2.0 — see the [LICENSE](LICENSE) file for details.

---

## 📬 Contact

**Ojas K** — [@ojask7](https://github.com/ojask7)

Project Link: [https://github.com/ojask7/macro-sign-service](https://github.com/ojask7/macro-sign-service)
