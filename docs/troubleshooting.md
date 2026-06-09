# Troubleshooting

## Authentication Issues

**401 Errors**: Verify credentials:
```bash
grep -A 5 '"auth"' config.json
```

If the service started without a config file (environment-variable fallback),
authentication is enabled but no credentials are configured, so all
authenticated endpoints return 401. Provide a config file with an `auth`
section or disable authentication.

## SSL Issues

**Certificate not found**:
```bash
ls -la ssl-certs/
```

**Verify certificate**:
```bash
openssl x509 -in ssl-certs/portal-conductor.crt -text -noout
```

## Logs

```bash
# Local
./portal-conductor

# Kubernetes
kubectl logs deployment/portal-conductor
```

All log output goes to stderr, including a line for each request with its
method, path, and response status.
