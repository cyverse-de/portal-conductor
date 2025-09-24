FROM haproxy:alpine

# Copy HAProxy configuration
COPY haproxy.cfg /usr/local/etc/haproxy/haproxy.cfg

# Expose SMTP port and stats port
EXPOSE 25 8404

# Validate configuration at build time
RUN haproxy -f /usr/local/etc/haproxy/haproxy.cfg -c

# Use default haproxy entrypoint and command
# The image already runs as haproxy user by default