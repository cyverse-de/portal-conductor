#!/usr/bin/env python3
"""
Startup script for Portal Conductor with optional SSL support.

This script reads the configuration and starts uvicorn with appropriate
SSL settings based on the configuration.
"""

import json
import os
import sys
import uvicorn

def load_config():
    """Load configuration from JSON file or environment variables as fallback."""
    config_file = os.environ.get("PORTAL_CONDUCTOR_CONFIG", "config.json")

    # Try to load from JSON file first
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                print(f"Loaded configuration from {config_file}", file=sys.stderr)
                return config
        except Exception as e:
            print(f"Failed to load config from {config_file}: {e}", file=sys.stderr)
            print("Falling back to environment variables", file=sys.stderr)

    # Fallback to environment variables (basic SSL config)
    config = {
        "ssl": {
            "enabled": os.environ.get("SSL_ENABLED", "true").lower() in ["1", "true", "yes"],
            "cert_file": os.environ.get("SSL_CERT_FILE", "/etc/ssl/certs/portal-conductor.crt"),
            "key_file": os.environ.get("SSL_KEY_FILE", "/etc/ssl/private/portal-conductor.key"),
            "port": int(os.environ.get("SSL_PORT", "8443"))
        },
        "server": {
            "http_port": int(os.environ.get("HTTP_PORT", "8000"))
        }
    }

    return config

def main():
    """Main startup function."""
    # Load configuration
    config = load_config()

    # Extract SSL and server configuration
    ssl_config = config.get("ssl", {})
    server_config = config.get("server", {})

    ssl_enabled = ssl_config.get("enabled", False)
    ssl_cert_file = ssl_config.get("cert_file")
    ssl_key_file = ssl_config.get("key_file")
    ssl_port = ssl_config.get("port", 8443)
    http_port = server_config.get("http_port", 8000)

    # Determine which mode to run in
    if ssl_enabled:
        # Check if SSL files exist
        if ssl_cert_file and ssl_key_file and os.path.exists(ssl_cert_file) and os.path.exists(ssl_key_file):
            print(f"Starting Portal Conductor with HTTPS on port {ssl_port}", file=sys.stderr)
            print(f"SSL Certificate: {ssl_cert_file}", file=sys.stderr)
            print(f"SSL Key: {ssl_key_file}", file=sys.stderr)

            uvicorn.run(
                "main:app",
                host="0.0.0.0",
                port=ssl_port,
                ssl_keyfile=ssl_key_file,
                ssl_certfile=ssl_cert_file,
                reload=False,
                access_log=True
            )
        else:
            print("SSL enabled but certificate files not found or not accessible:", file=sys.stderr)
            print(f"  Certificate: {ssl_cert_file} (exists: {os.path.exists(ssl_cert_file) if ssl_cert_file else False})", file=sys.stderr)
            print(f"  Key: {ssl_key_file} (exists: {os.path.exists(ssl_key_file) if ssl_key_file else False})", file=sys.stderr)
            print("Falling back to HTTP mode", file=sys.stderr)

            uvicorn.run(
                "main:app",
                host="0.0.0.0",
                port=http_port,
                reload=False,
                access_log=True
            )
    else:
        print(f"Starting Portal Conductor with HTTP on port {http_port}", file=sys.stderr)
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=http_port,
            reload=False,
            access_log=True
        )

if __name__ == "__main__":
    main()