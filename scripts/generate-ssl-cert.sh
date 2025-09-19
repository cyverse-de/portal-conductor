#!/bin/bash
#
# generate-ssl-cert.sh
#
# Script to generate self-signed SSL certificates for portal-conductor development
# For production, use proper certificates from a CA or cert-manager
#

set -e

CERT_DIR="./ssl-certs"
CERT_NAME="portal-conductor"
DAYS=365

# Create certificate directory
mkdir -p "$CERT_DIR"

echo "Generating self-signed SSL certificate for portal-conductor..."
echo "Certificate will be valid for $DAYS days"

# Generate private key
openssl genrsa -out "$CERT_DIR/$CERT_NAME.key" 2048

# Generate certificate signing request
openssl req -new -key "$CERT_DIR/$CERT_NAME.key" -out "$CERT_DIR/$CERT_NAME.csr" \
    -subj "/C=US/ST=Arizona/L=Tucson/O=CyVerse/OU=Development/CN=portal-conductor/emailAddress=support@cyverse.org"

# Generate self-signed certificate
openssl x509 -req -in "$CERT_DIR/$CERT_NAME.csr" -signkey "$CERT_DIR/$CERT_NAME.key" \
    -out "$CERT_DIR/$CERT_NAME.crt" -days $DAYS \
    -extensions v3_req -extfile <(
    echo '[v3_req]'
    echo 'basicConstraints = CA:FALSE'
    echo 'keyUsage = nonRepudiation, digitalSignature, keyEncipherment'
    echo 'subjectAltName = @alt_names'
    echo '[alt_names]'
    echo 'DNS.1 = portal-conductor'
    echo 'DNS.2 = localhost'
    echo 'IP.1 = 127.0.0.1'
    echo 'IP.2 = ::1'
)

# Clean up CSR
rm "$CERT_DIR/$CERT_NAME.csr"

# Set appropriate permissions
chmod 600 "$CERT_DIR/$CERT_NAME.key"
chmod 644 "$CERT_DIR/$CERT_NAME.crt"

echo "SSL certificate generated successfully!"
echo "Certificate: $CERT_DIR/$CERT_NAME.crt"
echo "Private Key: $CERT_DIR/$CERT_NAME.key"
echo ""
echo "To use with Docker:"
echo "  docker run -v \$(pwd)/$CERT_DIR:/etc/ssl/certs -v \$(pwd)/$CERT_DIR:/etc/ssl/private ..."
echo ""
echo "To create Kubernetes secret:"
echo "  kubectl create secret tls portal-conductor-ssl \\"
echo "    --cert=$CERT_DIR/$CERT_NAME.crt \\"
echo "    --key=$CERT_DIR/$CERT_NAME.key"
echo ""
echo "NOTE: This is a self-signed certificate for development only."
echo "For production, use certificates from a trusted CA."