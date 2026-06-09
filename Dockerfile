FROM golang:1.24 AS build

WORKDIR /src

# Download dependencies first for better caching
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build -o /portal-conductor .

FROM debian:bookworm-slim

# CA certificates are needed for TLS connections to Keycloak and other services
RUN apt update -y && \
    apt install -y --no-install-recommends ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=build /portal-conductor /usr/local/bin/portal-conductor

# Expose ports for both HTTP and HTTPS
EXPOSE 8000 8443

CMD ["portal-conductor"]
