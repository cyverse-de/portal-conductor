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
- **Formation Integration**: Async user deletion via Formation batch jobs
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
  },
  "smtp": {
    "host": "your-smtp-server.com",
    "port": 587,
    "user": "your-smtp-username",
    "password": "your-smtp-password",
    "use_tls": true,
    "use_ssl": false,
    "from": "noreply@yourdomain.com"
  },
  "formation": {
    "base_url": "http://formation:8080",
    "keycloak": {
      "server_url": "https://keycloak.example.com",
      "realm": "CyVerse",
      "client_id": "portal-conductor-service",
      "client_secret": "your-client-secret-here"
    },
    "user_deletion_app_id": "",
    "user_deletion_app_name": "portal-delete-user",
    "system_id": "de"
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
export SMTP_HOST=your-smtp-server.com
export SMTP_PORT=587
export SMTP_USER=your-smtp-username
export SMTP_PASSWORD=your-smtp-password
export SMTP_USE_TLS=true
export SMTP_FROM=noreply@yourdomain.com
```

**Note**: The JSON configuration file takes precedence over environment variables.

### SMTP Configuration

Portal Conductor supports sending emails through external SMTP servers. Configure SMTP settings in the `smtp` section of your config.json:

```json
{
  "smtp": {
    "host": "your-smtp-server.com",
    "port": 587,
    "user": "your-smtp-username",
    "password": "your-smtp-password",
    "use_tls": true,
    "use_ssl": false,
    "from": "noreply@yourdomain.com"
  }
}
```

**SMTP Options:**
- `host`: SMTP server hostname
- `port`: SMTP server port (587 for STARTTLS, 465 for SSL, 25 for plain)
- `user`: SMTP authentication username
- `password`: SMTP authentication password
- `use_tls`: Enable STARTTLS encryption (recommended for port 587)
- `use_ssl`: Enable SSL encryption (for port 465)
- `from`: Default sender address for outgoing emails

**Common SMTP Configurations:**
- **STARTTLS (Port 587)**: Set `use_tls: true, use_ssl: false`
- **SSL (Port 465)**: Set `use_tls: false, use_ssl: true`
- **Plain (Port 25)**: Set `use_tls: false, use_ssl: false` (not recommended for production)

If your SMTP server supports DKIM signing, it will be handled automatically by the server when emails are sent.

### Formation Configuration

Portal Conductor integrates with the Formation service to support asynchronous user deletion via batch jobs. This is particularly useful for users with large home directories where synchronous deletion would timeout.

**Configuration:**
```json
{
  "formation": {
    "base_url": "http://formation:8080",
    "keycloak": {
      "server_url": "https://keycloak.example.com",
      "realm": "CyVerse",
      "client_id": "portal-conductor-service",
      "client_secret": "your-client-secret-here"
    },
    "user_deletion_app_id": "",
    "user_deletion_app_name": "portal-delete-user",
    "system_id": "de"
  }
}
```

**Formation Options:**
- `base_url`: Formation API base URL
- `keycloak`: OAuth2 authentication configuration for Formation
  - `server_url`: Keycloak server URL
  - `realm`: Keycloak realm name
  - `client_id`: Service client ID for authentication
  - `client_secret`: Service client secret
- `user_deletion_app_id`: UUID of the deletion app (optional if using app name)
- `user_deletion_app_name`: Name of the deletion app (automatically resolved to ID at startup)
- `system_id`: Formation system identifier (typically "de")

**App Configuration:**
You can specify the user deletion app either by:
1. **Direct ID**: Set `user_deletion_app_id` to the app UUID
2. **App Name**: Set `user_deletion_app_name` (ID is looked up automatically at startup)

Using app name is more flexible when the app ID might change across environments.

**Async Deletion Endpoints:**
- `DELETE /async/users/{username}` - Submit user deletion job
- `GET /async/status/{analysis_id}` - Check deletion job status

See the [API Documentation](#api-documentation) section for detailed endpoint usage.

## Username Propagation and App-Exposer Whitelist

Portal Conductor integrates with multiple services to orchestrate job launches and user operations. When jobs are submitted through Portal Conductor, the username flows through a chain of services before reaching app-exposer for whitelist-based resource tracking bypass.

### Service Flow

**Complete job submission chain:**
```
portal-conductor → formation → apps → app-exposer
```

1. **Portal Conductor** → Calls Formation's `/app/launch/{system_id}/{app_id}` endpoint
2. **Formation** → Extracts username from JWT and calls apps service `/analyses` endpoint
3. **Apps** → Routes jobs to app-exposer based on job type:
   - VICE (interactive) apps → `POST /vice/launch`
   - Batch apps → `POST /batch` (JEX-compatible endpoint)
4. **App-Exposer** → Checks username against whitelist and optionally bypasses resource tracking

### Username Handling

**For service accounts (when Portal Conductor calls Formation):**

Formation applies username sanitization before passing to downstream services:
- **Removes all non-alphanumeric characters** (hyphens, underscores, dots, etc.)
- **Converts to lowercase**
- Only letters and numbers are retained

**Examples of transformation:**
- `de-service-account` → `deserviceaccount`
- `portal-conductor-service` → `portalconductorservice`
- `Service_Account_123` → `serviceaccount123`

**For regular users (when end users launch jobs):**
- Username is passed through without sanitization
- Uses the short form (without domain suffix)
- Example: `testuser` remains `testuser`

### App-Exposer Whitelist Configuration

App-exposer supports bypassing resource tracking (quota enforcement, concurrent job limits) for whitelisted users. The whitelist is configured in app-exposer's `config.yml`:

```yaml
resource_tracking:
  bypass_users:
    - deserviceaccount       # Sanitized form for "de-service-account"
    - adminuser              # Regular username
    - testuser123            # Another user
```

**CRITICAL:** When adding service account usernames to the app-exposer whitelist, you must use the **sanitized form** that Formation sends, not the original form from your configuration.

**Incorrect whitelist entry (will not match):**
```yaml
resource_tracking:
  bypass_users:
    - de-service-account    # ❌ Will NOT work - this has hyphens
```

**Correct whitelist entry (will match):**
```yaml
resource_tracking:
  bypass_users:
    - deserviceaccount      # ✅ Correct - sanitized form without hyphens
```

### Verifying Your Configuration

To verify your whitelist configuration is correct:

1. **Check Formation's service account username mapping** (in Formation's config.json):
   ```json
   {
     "service_account_usernames": {
       "app-runner": "de-service-account"
     }
   }
   ```

2. **Sanitize the username** - Remove all non-alphanumeric characters and lowercase:
   - `de-service-account` → `deserviceaccount`

3. **Add sanitized form to app-exposer whitelist** (in app-exposer's config.yml):
   ```yaml
   resource_tracking:
     bypass_users:
       - deserviceaccount
   ```

4. **Check app-exposer logs** when a job is submitted to confirm:
   ```
   Resource tracking disabled for user deserviceaccount (in bypass whitelist), skipping validation
   ```

### When Whitelist Bypass Applies

Users in the whitelist bypass the following checks:

**For VICE (interactive) apps:**
- Concurrent job limits
- Job limit configuration checks
- Resource usage overages from QMS (Quota Management Service)

**For batch apps:**
- Resource usage overages from QMS (Quota Management Service)

**Note:** Jobs are still created, tracked, and logged normally. Only the validation step is bypassed.

For more details on Formation's username sanitization, see the [Formation README](https://github.com/cyverse-de/formation/blob/main/README.md#service-account-username-mapping).

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

**User Management:**
- `POST /users/` - Create complete user account (LDAP + DataStore)
- `DELETE /users/{username}` - Delete user synchronously (LDAP + DataStore only)
- `POST /users/{username}/password` - Change user password
- `POST /users/{username}/validate` - Validate user credentials

**Async Operations (Formation):**
- `DELETE /async/users/{username}` - Delete user asynchronously (all systems including DB)
- `GET /async/status/{analysis_id}` - Check deletion job status

**LDAP Management:**
- `POST /ldap/users/` - Create LDAP user only
- `GET /ldap/users/{username}` - Get LDAP user information
- `GET /ldap/groups` - List all LDAP groups
- `POST /ldap/users/{username}/groups/{groupname}` - Add user to group

**DataStore Management:**
- `POST /datastore/users/` - Create DataStore user only
- `POST /datastore/users/{username}/services` - Register DataStore services
- `GET /datastore/users/{username}/exists` - Check if user exists in DataStore

**Other Services:**
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