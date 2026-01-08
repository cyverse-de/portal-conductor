# Development

## Project Structure

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

## Startup Scripts

- **`start_dual.py`** (recommended): Runs HTTPS (full API) + HTTP (health only)
- **`start.py`** (fallback): Runs single port (HTTPS or HTTP)

## Running Tests

```bash
uv run pytest
```

## Code Formatting

```bash
uv run ruff check .
uv run ruff check . --fix
```

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
