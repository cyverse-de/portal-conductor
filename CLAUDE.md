# Code Guidelines
* Keep code succinct.
* Add validation both in the backend and frontend.
* Don't repeat yourself needlessly.
* Prefer composition over inheritance for new first-party types.
* Use table-driven tests rather than lots of small, similar tests.
* Add doc comments to publicly available methods and functions.
* Document code succinctly but thoroughly.
* Generally treat warnings as errors unless fixing the warning would cause difficult to fix breakages.

# Tooling
* This is a Go project. Use `go build`, `go test`, `gofmt`, `go vet`, and `golangci-lint`.
* If available, use podman when building images instead of Docker.

# Other important projects
* portal-conductor: Usually available at ../portal-conductor/. Provides an API for the portal.

# Commands
- npm run dev: Run the portal locally
- curl -k https://portal-conductor/: Test if the portal-conductor is available locally.

