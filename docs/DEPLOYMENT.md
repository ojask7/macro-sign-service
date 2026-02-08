# Deployment Guide

## Quick Start with Docker Compose

```bash
# Clone the repository
git clone https://github.com/ojask7/macro-sign-service.git
cd macro-sign-service

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start all services
docker-compose up -d

# Verify services are running
curl http://localhost:8000/api/v1/health
```

## Kubernetes Deployment with Helm

### Prerequisites

- Kubernetes cluster (1.24+)
- Helm 3.x
- kubectl configured
- Container registry access

### Installation

```bash
# Add the chart repository
helm repo add macro-sign https://ojask7.github.io/macro-sign-service/charts

# Create namespace
kubectl create namespace macro-sign

# Create secrets
kubectl create secret generic macro-sign-secrets \
  --namespace macro-sign \
  --from-literal=app-secret-key=$(openssl rand -hex 32) \
  --from-literal=jwt-secret-key=$(openssl rand -hex 32) \
  --from-literal=database-url="postgresql+asyncpg://user:pass@host:5432/macrosign"

# Install the chart
helm install macro-sign ./deploy/helm/macro-sign-service \
  --namespace macro-sign \
  --values production-values.yaml

# Check status
kubectl get pods -n macro-sign
```

### Production Values Example

```yaml
# production-values.yaml
global:
  environment: production

api:
  replicaCount: 3
  image:
    tag: "v1.0.0"
  env:
    CERT_STORE_BACKEND: hashicorp_vault
  resources:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: 2000m
      memory: 1Gi

worker:
  replicaCount: 3
  concurrency: 8

ingress:
  enabled: true
  hosts:
    - host: macro-sign.yourcompany.com
      paths:
        - path: /api
          backend: api
        - path: /
          backend: dashboard
  tls:
    - secretName: macro-sign-tls
      hosts:
        - macro-sign.yourcompany.com

secrets:
  existingSecret: macro-sign-secrets

monitoring:
  enabled: true
```

## Monitoring

### Prometheus

The API exposes metrics at `/metrics` endpoint. Prometheus scraping is configured automatically via ServiceMonitor when using Helm.

### Grafana

A pre-built Grafana dashboard is included at `deploy/monitoring/grafana/dashboards/`.

Access Grafana:
- Docker Compose: http://localhost:3001 (admin/admin)
- Kubernetes: Configure via Helm values

### Key Metrics

| Metric | Description |
|--------|-------------|
| `http_requests_total` | Total HTTP requests |
| `http_request_duration_seconds` | Request latency histogram |
| `http_requests_in_progress` | Currently active requests |

## Operations Runbook

### Common Issues

1. **Service returns 503**: Check database and Redis connectivity
2. **Signing jobs stuck in "queued"**: Verify Celery worker is running
3. **Certificate errors**: Check certificate store connectivity and expiry
4. **Rate limiting**: Adjust `RATE_LIMIT_REQUESTS_PER_MINUTE` in config

### Scaling

- **API**: Increase `api.replicaCount` or enable HPA
- **Workers**: Increase `worker.replicaCount` and `worker.concurrency`
- **Database**: Use read replicas for query-heavy workloads

### Backup

```bash
# Database backup
pg_dump -h localhost -U macrosign macrosign > backup.sql

# Restore
psql -h localhost -U macrosign macrosign < backup.sql
```
