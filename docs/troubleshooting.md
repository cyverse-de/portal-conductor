# Troubleshooting

## Authentication Issues

**401 Errors**: Verify credentials:
```bash
grep -A 5 '"auth"' config.json
```

**Test password hash**:
```bash
uv run python -c "from handlers.auth import verify_password; print(verify_password('your_password', 'hash_from_config'))"
```

## SSL Issues

**Certificate not found**:
```bash
ls -la ssl-certs/
```

**Verify certificate**:
```bash
openssl x509 -in ssl-certs/portal-conductor.crt -text -noout
```

## Common Warnings

**bcrypt version warning** (harmless):
```
(trapped) error reading bcrypt version
AttributeError: module 'bcrypt' has no attribute '__about__'
```
This is a compatibility issue between `passlib` 1.7.4 and `bcrypt` 4.x. Authentication still works correctly.

## Dependencies

```bash
uv sync
```

## Logs

```bash
# Local
uv run python start.py

# Kubernetes
kubectl logs deployment/portal-conductor
```
