# Minimal Dockerfile for running the delete-user CLI
# This is designed to be used as a batch job in the Discovery Environment

FROM golang:1.24 AS build

WORKDIR /src

# Download dependencies first for better caching
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build -o /delete-user ./cmd/delete-user

FROM debian:bookworm-slim

# CA certificates are needed for TLS connections to Mailman and other services
RUN apt update -y && \
    apt install -y --no-install-recommends ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=build /delete-user /usr/local/bin/delete-user

ENTRYPOINT ["delete-user"]

# Default command shows help (can be overridden with username argument)
CMD ["--help"]
