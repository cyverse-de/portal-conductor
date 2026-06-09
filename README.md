# Portal Conductor

A service that orchestrates calls to `portal-ldap`, `portal-datastore`, Terrain, and mailing list services for managing user accounts and services in the CyVerse platform.

The server and the standalone `delete-user` batch job are written in Go:

- `main.go` — the API server (built by `Dockerfile`)
- `cmd/delete-user` — the user-deletion CLI run as a Discovery Environment
  batch job (built by `DeleteUser.dockerfile`); it reads the same config file
  plus a `portal_db` section (see `scripts/delete-user.example.json`)

## Quick Start

### 1. Configure

```bash
cp config.template.json config.json
```

Edit `config.json` with your service credentials (LDAP, iRODS, Terrain, etc.)
and set `auth.username`/`auth.password` for HTTP Basic authentication.

### 2. Generate SSL Certificates (Optional)

```bash
./scripts/generate-ssl-cert.sh
```

### 3. Build and Run

```bash
go build -o portal-conductor .
./portal-conductor
```

When SSL is enabled with certificates available, the service runs in dual-port mode:
- **HTTPS port 8443**: Full API with authentication
- **HTTP port 8000**: Health checks only (always available)

Without SSL it serves the full API over HTTP on port 8000. The
`--http-port` and `--https-port` flags override the configured ports.

### 4. Test

```bash
# Run the unit tests
go test ./...

# Health check (no auth required)
curl -k https://localhost:8443/

# Authenticated endpoint
curl -k -u admin:your_password https://localhost:8443/ldap/users/test/exists
```

## Documentation

- [Configuration](docs/configuration.md) - Detailed configuration options
- [Authentication](docs/authentication.md) - HTTP Basic Auth setup
- [SSL/HTTPS](docs/ssl.md) - SSL certificate configuration
- [API Reference](docs/api.md) - Endpoint documentation
- [Development](docs/development.md) - Project structure and testing
- [Troubleshooting](docs/troubleshooting.md) - Common issues and solutions
- [Username Propagation](docs/username-propagation.md) - Service account handling
