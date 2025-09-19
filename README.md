# Portal Conductor

A service that orchestrates calls to `portal-ldap`, `portal-datastore`, Terrain, and mailing list services for managing user accounts and services in the CyVerse platform.

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Authentication](#authentication)
- [SSL/HTTPS Support](#sslhttps-support)
- [API Documentation](#api-documentation)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

## Features

- **User Management**: Create and manage LDAP users with group memberships
- **DataStore Integration**: Set up iRODS users with permissions and service registrations
- **Terrain Integration**: Manage VICE job limits for users
- **Mailing List Management**: Add/remove users from Mailman mailing lists
- **Email Services**: Send notification emails for user operations
- **HTTP Basic Authentication**: Secure all endpoints with configurable credentials
- **HTTPS Support**: Optional SSL/TLS encryption with automatic HTTP fallback
- **OpenAPI Documentation**: Interactive Swagger UI for API exploration

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

### 2. Configure

Copy the template configuration:

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

Single-port fallback mode:
```bash
uv run python start.py  # HTTP only if certificates missing
```

### 6. Test

```bash
# Health check (no auth required)
curl -k https://localhost:8443/

# Authenticated endpoint
curl -k -u admin:your_password https://localhost:8443/users/test/exists
```

## Configuration

Portal Conductor uses a JSON configuration file that defines all service connections and settings. Start by copying the provided template:

```bash
cp config.template.json config.json
```

The `config.template.json` file contains all required configuration sections with example values. Edit `config.json` to match your environment.

### Full Configuration Format

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
  },
  "auth": {
    "enabled": true,
    "username": "admin",
    "password": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj0kB.z8.6X2",
    "realm": "Portal Conductor API"
  },
  "ldap": {
    "url": "ldap://your-ldap-server:389",
    "user": "cn=admin,dc=example,dc=com",
    "password": "your-ldap-password",
    "base_dn": "dc=example,dc=com",
    "community_group": "community",
    "everyone_group": "everyone"
  },
  "irods": {
    "host": "your-irods-server",
    "port": "1247",
    "user": "your-irods-admin-user",
    "password": "your-irods-password",
    "zone": "your-irods-zone",
    "admin_user": "rodsadmin",
    "ipcservices_user": "ipcservices"
  },
  "terrain": {
    "url": "http://your-terrain-server/",
    "user": "your-terrain-user",
    "password": "your-terrain-password"
  },
  "mailman": {
    "enabled": false,
    "url": "http://your-mailman-server/",
    "password": "your-mailman-password"
  }
}
```

### Environment Variables

As a fallback, configuration can be provided via environment variables:

```bash
export LDAP_URL=ldap://your-ldap-server:389
export LDAP_USER=cn=admin,dc=example,dc=com
export LDAP_PASSWORD=your-ldap-password
export LDAP_BASE_DN=dc=example,dc=com
export IRODS_HOST=your-irods-server
export IRODS_USER=your-irods-admin
export TERRAIN_URL=http://your-terrain-server/
export AUTH_USERNAME=admin
export AUTH_PASSWORD="$2b$12$..."
```

**Note**: The JSON configuration file takes precedence over environment variables.

## Authentication

Portal Conductor uses HTTP Basic Authentication by default.

### Generate Password Hash

```bash
# Interactive script
uv run python scripts/generate-password-hash.py

# Command line
uv run python -c "from handlers.auth import get_password_hash; print(get_password_hash('your_password'))"
```

### Using the API

```bash
# Basic auth
curl -u admin:password https://localhost:8443/users/john/exists

# Authorization header
curl -H "Authorization: Basic $(echo -n 'admin:password' | base64)" \
     https://localhost:8443/users/john/exists
```

### Swagger UI

1. Navigate to `/docs` (e.g., https://localhost:8443/docs)
2. Click **"Authorize"** button
3. Enter username and password
4. Test endpoints interactively

### Disable Authentication

For development only:

```json
{
  "auth": {
    "enabled": false
  }
}
```

## SSL/HTTPS Support

SSL is enabled by default with automatic HTTP fallback.

### Generate Development Certificates

```bash
./scripts/generate-ssl-cert.sh
```

### Configure SSL

```json
{
  "ssl": {
    "enabled": true,
    "cert_file": "./ssl-certs/portal-conductor.crt",
    "key_file": "./ssl-certs/portal-conductor.key",
    "port": 8443
  }
}
```

### Behavior

- **SSL Enabled + Certificates Found**: HTTPS on port 8443
- **SSL Enabled + Certificates Missing**: HTTP on port 8000 (fallback)
- **SSL Disabled**: HTTP on port 8000

## API Documentation

Interactive API documentation is available at:

- **Swagger UI**: https://localhost:8443/docs
- **ReDoc**: https://localhost:8443/redoc
- **OpenAPI JSON**: https://localhost:8443/openapi.json

### Key Endpoints

- `POST /users/` - Create complete user account (LDAP + DataStore + Email)
- `POST /ldap/users/` - Create LDAP user only
- `POST /datastore/users/` - Create DataStore user only
- `GET /users/{username}/exists` - Check if user exists across all systems
- `POST /datastore/users/{username}/services` - Register DataStore services
- `GET /terrain/users/{username}/job-limits` - Get VICE job limits
- `GET /mailinglists/{listname}/members` - List mailing list members

## Development

### Project Structure

```
portal-conductor/
├── handlers/           # API endpoint handlers
│   ├── auth.py        # Authentication logic
│   ├── user_management.py
│   ├── ldap_management.py
│   └── ...
├── scripts/           # Utility scripts
├── ssl-certs/         # SSL certificates (generated)
├── main.py           # FastAPI application
├── start_dual.py     # Dual-port startup (production)
├── start.py          # Single-port startup (fallback)
├── config.template.json
└── pyproject.toml
```

### Startup Scripts

- **`start_dual.py`** (recommended): Runs HTTPS (full API) + HTTP (health only)
- **`start.py`** (fallback): Runs single port (HTTPS or HTTP)

### Running Tests

```bash
uv run pytest
```

### Code Formatting

```bash
uv run ruff check .
uv run ruff check . --fix
```

## Troubleshooting

### Authentication Issues

**401 Errors**: Verify credentials:
```bash
grep -A 5 '"auth"' config.json
```

**Test password hash**:
```bash
uv run python -c "from handlers.auth import verify_password; print(verify_password('your_password', 'hash_from_config'))"
```

### SSL Issues

**Certificate not found**:
```bash
ls -la ssl-certs/
```

**Verify certificate**:
```bash
openssl x509 -in ssl-certs/portal-conductor.crt -text -noout
```

### Common Warnings

**bcrypt version warning** (harmless):
```
(trapped) error reading bcrypt version
AttributeError: module 'bcrypt' has no attribute '__about__'
```
This is a compatibility issue between `passlib` 1.7.4 and `bcrypt` 4.x. Authentication still works correctly.

### Dependencies

```bash
uv sync
```

### Logs

```bash
# Local
uv run python start.py
```

---

For detailed authentication and SSL configuration, see:
- [AUTH_README.md](AUTH_README.md)
- [SSL_README.md](SSL_README.md)