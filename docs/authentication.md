# Portal Conductor Authentication

Portal Conductor supports HTTP Basic Authentication to secure API endpoints. Authentication is enabled by default.

## Quick Setup

### 1. Configure Authentication

Edit `config.json`:

```json
{
  "auth": {
    "enabled": true,
    "username": "admin",
    "password": "your-strong-password",
    "realm": "Portal Conductor API"
  }
}
```

The password is stored in plaintext in the config file and compared in
constant time, so protect the config file itself (file permissions,
Kubernetes secrets).

**⚠️ Use a strong, unique password.**

### 2. Test Authentication

```bash
# Health check (no auth required) - works on both ports
curl http://localhost:8000/
curl -k https://localhost:8443/

# Authenticated endpoint - HTTPS only (HTTP port blocks API endpoints)
curl -k -u admin:your_password https://localhost:8443/ldap/users/test/exists
```

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

Authentication credentials live in the config file, so deploy the whole
config as a secret and mount it:

```bash
kubectl create secret generic portal-conductor-config \
  --from-file=config.json
```

```yaml
env:
  - name: PORTAL_CONDUCTOR_CONFIG
    value: /etc/portal-conductor/config.json
volumeMounts:
  - name: config
    mountPath: /etc/portal-conductor
    readOnly: true
volumes:
  - name: config
    secret:
      secretName: portal-conductor-config
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

## Security Notes

- API endpoints only accessible via HTTPS (HTTP port restricted to health checks)
- Use strong, unique passwords
- Rotate credentials regularly
- Store production credentials securely (Kubernetes secrets, Vault)
- Username and password comparisons use constant-time comparison to prevent timing attacks

## Troubleshooting

**401 Errors**: Verify credentials in config:
```bash
grep -A 5 '"auth"' config.json
```

Note that when no config file is found and the service falls back to
environment variables, authentication remains enabled but no credentials are
configured, so every authenticated endpoint returns 401. Provide a config
file with an `auth` section (or disable auth) to fix this.
