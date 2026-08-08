#!/bin/sh
# Single process: nginx handles HTTPS termination for LAN (9443), cloudflared connects here directly
exec uvicorn backend.api.main:app --host 0.0.0.0 --port 8080
