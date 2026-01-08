# Portal Conductor

A service that orchestrates calls to `portal-ldap`, `portal-datastore`, Terrain, and mailing list services for managing user accounts and services in the CyVerse platform.

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

### 2. Configure

```bash
cp config.template.json config.json
```

Edit `config.json` with your service credentials (LDAP, iRODS, Terrain, etc.).

### 3. Set Up Authentication

Generate a password hash:

```bash
uv run python scripts/generate-password-hash.py
```

Update the `auth.password` field in `config.json` with the generated hash.

### 4. Generate SSL Certificates (Optional)

```bash
./scripts/generate-ssl-cert.sh
```

### 5. Run

```bash
uv run python start_dual.py
```

The service runs in dual-port mode:
- **HTTPS port 8443**: Full API with authentication (when certificates available)
- **HTTP port 8000**: Health checks only (always available)

### 6. Test

```bash
# Health check (no auth required)
curl -k https://localhost:8443/

# Authenticated endpoint
curl -k -u admin:your_password https://localhost:8443/users/test/exists
```

## Documentation

- [Configuration](docs/configuration.md) - Detailed configuration options
- [Authentication](docs/authentication.md) - HTTP Basic Auth setup
- [SSL/HTTPS](docs/ssl.md) - SSL certificate configuration
- [API Reference](docs/api.md) - Endpoint documentation
- [Development](docs/development.md) - Project structure and testing
- [Troubleshooting](docs/troubleshooting.md) - Common issues and solutions
- [Username Propagation](docs/username-propagation.md) - Service account handling

Interactive API docs available at `/docs` (Swagger UI) and `/redoc` when running.
