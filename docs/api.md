# API Documentation

Interactive API documentation is available at:

- **Swagger UI**: https://localhost:8443/docs
- **ReDoc**: https://localhost:8443/redoc
- **OpenAPI JSON**: https://localhost:8443/openapi.json

## User Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/users/` | POST | Create complete user account (LDAP + DataStore) |
| `/users/{username}` | DELETE | Delete user synchronously (LDAP + DataStore only) |
| `/users/{username}/password` | POST | Change user password |
| `/users/{username}/validate` | POST | Validate user credentials |

## Async Operations (Formation)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/async/users/{username}` | DELETE | Delete user asynchronously (all systems including DB) |
| `/async/status/{analysis_id}` | GET | Check deletion job status |

## LDAP Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ldap/users/` | POST | Create LDAP user only |
| `/ldap/users/{username}` | GET | Get LDAP user information |
| `/ldap/groups` | GET | List all LDAP groups |
| `/ldap/users/{username}/groups/{groupname}` | POST | Add user to group |

## DataStore Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/datastore/users/` | POST | Create DataStore user only |
| `/datastore/users/{username}/services` | POST | Register DataStore services |
| `/datastore/users/{username}/exists` | GET | Check if user exists in DataStore |

## Other Services

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/terrain/users/{username}/job-limits` | GET | Get VICE job limits |
| `/mailinglists/{listname}/members` | GET | List mailing list members |
