# Development

## Project Structure

```
portal-conductor/
├── api/               # HTTP API: router, auth middleware, endpoint handlers
├── cmd/
│   └── delete-user/   # Standalone user-deletion CLI (DE batch job)
├── config/            # Config file / environment variable loading
├── datastore/         # iRODS client (go-irodsclient)
├── emailsvc/          # SMTP email sending
├── external/          # Error types for external HTTP service failures
├── formation/         # Formation client with Keycloak token management
├── kinds/             # Request/response body types
├── ldapclient/        # LDAP operations (go-ldap)
├── mailman/           # Mailman 2.1 admin interface client
├── portaldb/          # Portal PostgreSQL database access (delete-user)
├── terrain/           # Terrain API client
├── scripts/           # Utility scripts and config examples
├── ssl-certs/         # SSL certificates (generated)
├── main.go            # API server entrypoint
├── config.template.json
├── Dockerfile         # API server image
└── DeleteUser.dockerfile  # delete-user batch job image
```

## Building and Running

```bash
# API server
go build -o portal-conductor .
./portal-conductor

# delete-user CLI
go build -o delete-user ./cmd/delete-user
./delete-user --help
```

The server runs HTTPS (full API) plus HTTP (health checks only) when SSL is
enabled and certificates exist, and falls back to a single HTTP port
otherwise. See [SSL/HTTPS](ssl.md).

## Running Tests

```bash
go test ./...
```

## Linting and Formatting

```bash
gofmt -l .
go vet ./...
golangci-lint run ./...
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
