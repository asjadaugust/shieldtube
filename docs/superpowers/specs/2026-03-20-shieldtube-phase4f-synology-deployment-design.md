# Phase 4f: Synology NAS Deployment — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft
**Source:** [ShieldTube PRD](../../ShieldTube_PRD.md) — Phase 4: Polish + P1 Features

---

## Goal

Documentation guide for deploying ShieldTube on Synology NAS via Docker.

**Success criteria:** Follow the guide → ShieldTube running on Synology → accessible from Shield TV on LAN.

---

## Design

Write `docs/deployment/synology-nas.md` covering:

1. **Prerequisites** — Synology model requirements (Docker support), DSM version, available RAM/CPU
2. **Docker setup** — Install Docker via Package Center, SSH access
3. **Volume configuration** — Create shared folders for cache (`/volume1/shieldtube/cache`), DB (`/volume1/shieldtube/db`), config (`/volume1/shieldtube/config`)
4. **Docker Compose deployment** — Copy docker-compose.yml, adjust volume paths for Synology, set `FFMPEG_THREADS=2` (weak CPU), configure restart policy
5. **Network** — Static IP assignment, firewall port 8080, Shield TV → NAS connectivity test
6. **OAuth setup** — Google Cloud Console project, OAuth consent screen, client ID/secret, bootstrap token
7. **Pre-cache rules** — Copy precache_rules.json to config volume, customize channel IDs
8. **Monitoring** — Check logs via `docker-compose logs -f`, verify cache disk usage via API
9. **Updating** — Pull new image, restart container
10. **Troubleshooting** — Common issues (port conflicts, permission errors, FFmpeg OOM on weak CPU)

**No code changes.** Documentation only.

**Files:**

| File | Change |
|------|--------|
| `docs/deployment/synology-nas.md` | New: full deployment guide |

---

## What This Phase Does NOT Include

- Synology-specific Docker Compose override file
- Health check endpoints
- Auto-update mechanism
