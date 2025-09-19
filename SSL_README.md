# Portal Conductor SSL/HTTPS Support

Portal Conductor supports optional HTTPS/SSL configuration, enabled by default for secure communication.

## Quick Setup

### 1. Generate Development Certificates

```bash
./scripts/generate-ssl-cert.sh
```

Creates self-signed certificates in `ssl-certs/` directory.

### 2. Configure SSL

Edit `config.json`:

```json
{
  "ssl": {
    "enabled": true,
    "cert_file": "./ssl-certs/portal-conductor.crt",
    "key_file": "./ssl-certs/portal-conductor.key",
    "port": 8443
  },
  "server": {
    "http_port": 8000
  }
}
```

### 3. Run with SSL

```bash
uv run python start.py
```

Portal Conductor starts on HTTPS port 8443, falls back to HTTP port 8000 if certificates missing.

### 4. Test HTTPS

```bash
# Accept self-signed certificate
curl -k https://localhost:8443/

# Browser: Navigate to https://localhost:8443 (accept security warning)
```

## Environment Variables

```bash
export SSL_ENABLED=true
export SSL_CERT_FILE=./ssl-certs/portal-conductor.crt
export SSL_KEY_FILE=./ssl-certs/portal-conductor.key
export SSL_PORT=8443
export HTTP_PORT=8000
```

## Docker Usage

```bash
# Mount certificates from project directory
docker run -v $(pwd)/ssl-certs:/app/ssl-certs \
  -e SSL_CERT_FILE=/app/ssl-certs/portal-conductor.crt \
  -e SSL_KEY_FILE=/app/ssl-certs/portal-conductor.key \
  -p 8443:8443 portal-conductor
```

## Kubernetes Deployment

### 1. Create SSL Secret

```bash
# Development (self-signed)
./scripts/generate-ssl-cert.sh
kubectl create secret tls portal-conductor-ssl \
  --cert=ssl-certs/portal-conductor.crt \
  --key=ssl-certs/portal-conductor.key

# Production (real certificates)
kubectl create secret tls portal-conductor-ssl \
  --cert=/path/to/production.crt \
  --key=/path/to/production.key
```

### 2. Deploy and Access

```bash
kubectl apply -f k8s/portal-conductor.yml

# HTTPS access
kubectl port-forward svc/portal-conductor 8443:443

# HTTP fallback
kubectl port-forward svc/portal-conductor 8000:80
```

## Behavior

- **SSL Enabled + Certificates Found**: HTTPS on port 8443
- **SSL Enabled + Certificates Missing**: HTTP on port 8000 (fallback)
- **SSL Disabled**: HTTP on port 8000

## Disable SSL

```json
{
  "ssl": {
    "enabled": false
  }
}
```

Or via environment:
```bash
export SSL_ENABLED=false
```

## Production Notes

- Replace self-signed certificates with trusted CA certificates
- Use cert-manager for automatic certificate management in Kubernetes
- Configure network policies to restrict HTTP access if not needed

## Troubleshooting

**Certificate not found**:
```bash
ls -la ssl-certs/
```

**Check application logs**:
```bash
# Local
python start.py

# Kubernetes
kubectl logs deployment/portal-conductor
```

**Verify certificate**:
```bash
openssl x509 -in ssl-certs/portal-conductor.crt -text -noout
```