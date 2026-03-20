#!/usr/bin/env bash
# Generate a self-signed TLS certificate for ShieldTube.
# Usage: bash config/generate-cert.sh

set -euo pipefail

CERT_DIR="$(dirname "$0")/certs"
mkdir -p "$CERT_DIR"

openssl req -x509 -newkey rsa:4096 -nodes \
    -keyout "$CERT_DIR/key.pem" \
    -out "$CERT_DIR/cert.pem" \
    -days 3650 \
    -subj "/CN=shieldtube.local"

echo "Certificate generated at:"
echo "  $CERT_DIR/cert.pem"
echo "  $CERT_DIR/key.pem"
