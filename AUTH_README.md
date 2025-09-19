# Portal Conductor Authentication

Portal Conductor supports HTTP Basic Authentication to secure API endpoints. Authentication is enabled by default.

## Quick Setup

### 1. Generate Password Hash

```bash
# Using the dedicated script
uv run python scripts/generate-password-hash.py

# Or directly
uv run python -c "from handlers.auth import get_password_hash; print(get_password_hash('your_password'))"
```

### 2. Configure Authentication

Edit `config.json`:

```json
{
  "auth": {
    "enabled": true,
    "username": "admin",
    "password": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj0kB.z8.6X2",
    "realm": "Portal Conductor API"
  }
}
```

**⚠️ Change the default password immediately!** The hash above is for password `admin`.

### 3. Test Authentication

```bash
# Health check (no auth required) - works on both ports
curl http://localhost:8000/
curl -k https://localhost:8443/

# Authenticated endpoint - HTTPS only (HTTP port blocks API endpoints)
curl -k -u admin:your_password https://localhost:8443/users/test/exists
```

## Environment Variables

Configure via environment variables:

```bash
export AUTH_ENABLED=true
export AUTH_USERNAME=admin
export AUTH_PASSWORD="$2b$12$..."
export AUTH_REALM="Portal Conductor API"
```

## Swagger UI

1. Navigate to `/docs` (e.g., http://localhost:8000/docs)
2. Click **"Authorize"** button (lock icon)
3. Enter username and password
4. Click **"Authorize"**

## API Usage

### With Authentication

```bash
# Basic auth (HTTPS required for API endpoints)
curl -k -u username:password https://localhost:8443/ldap/users/john.doe/exists

# Authorization header
curl -k -H "Authorization: Basic $(echo -n 'username:password' | base64)" \
     https://localhost:8443/ldap/users/john.doe/exists
```

### Response Codes

- **200**: Valid credentials
- **401**: Invalid/missing credentials with `WWW-Authenticate: Basic realm="Portal Conductor API"`

## Kubernetes Deployment

### 1. Create Secret

```bash
# Generate hash
PASSWORD_HASH=$(uv run python -c "from handlers.auth import get_password_hash; print(get_password_hash('secure_password'))")

# Create secret
kubectl create secret generic portal-conductor-auth \
  --from-literal=username=admin \
  --from-literal=password="$PASSWORD_HASH"
```

### 2. Update Deployment

```yaml
env:
  - name: AUTH_USERNAME
    valueFrom:
      secretKeyRef:
        name: portal-conductor-auth
        key: username
  - name: AUTH_PASSWORD
    valueFrom:
      secretKeyRef:
        name: portal-conductor-auth
        key: password
```

## Disable Authentication

For development/testing:

```json
{
  "auth": {
    "enabled": false
  }
}
```

Or via environment:
```bash
export AUTH_ENABLED=false
```

## Security Notes

- Passwords stored as bcrypt hashes (cost factor 12)
- API endpoints only accessible via HTTPS (HTTP port restricted to health checks)
- Use strong, unique passwords
- Rotate credentials regularly
- Store production credentials securely (Kubernetes secrets, Vault)

## Troubleshooting

**401 Errors**: Verify credentials in config:
```bash
grep -A 5 '"auth"' config.json
```

**Test password hash**:
```bash
uv run python -c "from handlers.auth import verify_password; print(verify_password('your_password', 'hash_from_config'))"
```

**bcrypt version warning**: The following warning is harmless and can be ignored:
```
(trapped) error reading bcrypt version
AttributeError: module 'bcrypt' has no attribute '__about__'
```
This occurs due to a compatibility issue between `passlib` 1.7.4 and `bcrypt` 4.x. Authentication still works correctly.

**Dependencies**:
```bash
uv sync
```