# HTTPS Setup

ShieldTube uses a self-signed TLS certificate for LAN-only HTTPS.

## Generate Certificate

```bash
bash config/generate-cert.sh
```

This creates `config/certs/cert.pem` and `config/certs/key.pem` (10-year validity).

## Docker

The Docker image expects certs mounted at `/app/config/certs/`:

```bash
docker-compose up -d
```

The API serves on port **8443** over HTTPS.

## Manual (without Docker)

```bash
uvicorn backend.api.main:app \
    --host 0.0.0.0 --port 8443 \
    --ssl-keyfile config/certs/key.pem \
    --ssl-certfile config/certs/cert.pem
```

## Android Shield App

The app includes a `network_security_config.xml` that trusts user-installed CAs, allowing the self-signed cert to work on the Shield TV.

Install the `cert.pem` on the Shield device via:
1. Copy `cert.pem` to the device
2. Settings > Security > Install from storage

## Verification

```bash
curl -k https://localhost:8443/docs
```
