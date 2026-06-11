# Configuration

Portal Conductor uses a JSON configuration file that defines all service connections and settings.

## Setup

Copy the provided template:

```bash
cp config.template.json config.json
```

Edit `config.json` to match your environment.

## Full Configuration Format

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
    "password": "your-terrain-password",
    "user_deletion_app_id": "",
    "user_deletion_app_name": "portal-delete-user",
    "system_id": "de"
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
  }
}
```

## Environment Variables

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

## SMTP Configuration

Portal Conductor supports sending emails through external SMTP servers.

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

## Terrain Configuration

Portal Conductor uses the Terrain API both for job-limit management and for asynchronous user deletion via batch jobs. Authentication uses the configured service account: portal-conductor exchanges the basic-auth credentials for a Keycloak access token via Terrain's `/token/keycloak` endpoint.

```json
{
  "terrain": {
    "url": "http://your-terrain-server/",
    "user": "your-terrain-user",
    "password": "your-terrain-password",
    "user_deletion_app_id": "",
    "user_deletion_app_name": "portal-delete-user",
    "system_id": "de"
  }
}
```

**Terrain Options:**
- `url`: Terrain API base URL
- `user`: Service account username (also the user the deletion analyses run as)
- `password`: Service account password
- `user_deletion_app_id`: UUID of the deletion app (optional if using app name)
- `user_deletion_app_name`: Name of the deletion app (automatically resolved to ID at startup)
- `system_id`: DE system identifier (typically "de")

Environment variable fallbacks: `TERRAIN_URL`, `TERRAIN_USER`, `TERRAIN_PASSWORD`, `TERRAIN_USER_DELETION_APP_ID`, `TERRAIN_USER_DELETION_APP_NAME`, `TERRAIN_SYSTEM_ID`.

**App Configuration:**
You can specify the user deletion app either by:
1. **Direct ID**: Set `user_deletion_app_id` to the app UUID
2. **App Name**: Set `user_deletion_app_name` (ID is looked up automatically at startup)

Using app name is more flexible when the app ID might change across environments.

**Notes:**
- The deletion app must be public or shared with the configured Terrain user, since the analyses are submitted as that user.
- Analysis outputs are written under `/{irods.zone}/home/{terrain.user}/analyses/`, so `irods.zone` must match the zone of the Terrain user's home collection.
- To disable the async deletion endpoints, blank out both `user_deletion_app_id` and `user_deletion_app_name`; the `/async/*` endpoints then return 503.
