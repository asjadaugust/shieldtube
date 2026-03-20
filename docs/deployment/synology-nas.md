# ShieldTube Deployment: Synology NAS

## Prerequisites

- Synology NAS with Docker support (DS218+, DS920+, DS1621+, or newer)
- DSM 7.0 or later
- At least 2GB free RAM
- Docker package installed via Package Center
- SSH access enabled (Control Panel → Terminal & SNMP → Enable SSH)
- NVIDIA Shield TV on the same LAN

## 1. Create Shared Folders

Via DSM File Station or SSH:

```bash
mkdir -p /volume1/shieldtube/cache
mkdir -p /volume1/shieldtube/db
mkdir -p /volume1/shieldtube/config
```

## 2. Configure Environment

Create `/volume1/shieldtube/config/.env`:

```bash
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8080
CACHE_DIR=/app/cache
DB_PATH=/app/db/shieldtube.db
FFMPEG_THREADS=2

# Google OAuth (from Google Cloud Console)
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here

# Bootstrap token (from Google OAuth Playground — optional if using device flow)
YOUTUBE_ACCESS_TOKEN=
YOUTUBE_REFRESH_TOKEN=

# Thumbnail settings
THUMBNAIL_CONCURRENCY=5
DOWNLOAD_WAIT_TIMEOUT=30
```

**Note:** Set `FFMPEG_THREADS=2` for Synology NAS. The CPU is weak — more threads won't help and may cause OOM.

## 3. Deploy with Docker Compose

Create `/volume1/shieldtube/docker-compose.yml`:

```yaml
version: '3.8'
services:
  shieldtube-api:
    build:
      context: ./app/backend
      dockerfile: Dockerfile
    ports:
      - "8080:8080"
    volumes:
      - /volume1/shieldtube/cache:/app/cache
      - /volume1/shieldtube/db:/app/db
      - /volume1/shieldtube/config:/app/config
    env_file:
      - /volume1/shieldtube/config/.env
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G
```

Or pull the pre-built image (if published):

```yaml
services:
  shieldtube-api:
    image: shieldtube/api:latest
    # ... same ports, volumes, env_file, restart ...
```

## 4. Build and Start

SSH into your Synology:

```bash
ssh admin@your-nas-ip

cd /volume1/shieldtube

# Clone the repo (or copy files)
git clone https://github.com/youruser/shieldtube.git app

# Build and start
cd app
docker-compose up -d

# Verify it's running
docker-compose ps
curl http://localhost:8080/docs
```

## 5. Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project: "ShieldTube"
3. Enable the **YouTube Data API v3**
4. Go to **OAuth consent screen** → External → fill in app name
5. Add scopes: `youtube.readonly`, `youtube.force-ssl`
6. Go to **Credentials** → Create OAuth client ID → TV/Limited Input
7. Copy Client ID and Client Secret to `.env`

### Bootstrap Token (Quick Start)

For immediate testing without the device flow:

1. Go to [OAuth Playground](https://developers.google.com/oauthplayground/)
2. Settings gear → Use your own OAuth credentials → enter Client ID/Secret
3. Authorize: `https://www.googleapis.com/auth/youtube.readonly`
4. Exchange for tokens
5. Copy access_token and refresh_token to `.env`
6. Restart: `docker-compose restart`

### Device Flow (Production)

Once the app is running with Client ID/Secret:

1. Open Shield TV → ShieldTube app (or curl):
   ```bash
   curl http://your-nas-ip:8080/api/auth/login
   ```
2. Note the `user_code` and `verification_url`
3. On your phone, go to `google.com/device` and enter the code
4. Poll for completion:
   ```bash
   curl "http://your-nas-ip:8080/api/auth/callback?device_code=YOUR_DEVICE_CODE"
   ```

## 6. Configure Pre-caching Rules

Edit `/volume1/shieldtube/config/precache_rules.json`:

```json
{
  "precache_rules": [
    {
      "type": "channel",
      "channel_id": "UCxxxxxxxxxxxxxxxxxxxxxx",
      "max_videos": 5,
      "quality": "1080p",
      "trigger": "on_upload"
    }
  ]
}
```

Find channel IDs: go to a YouTube channel page → view page source → search for `channelId`.

## 7. Configure Shield TV

On the Shield app, update the backend URL to point to your NAS:

The `BACKEND_HOST` constant in the Shield app must match your NAS IP. For Phase 4, this is hardcoded in `ApiClient.kt` and `PlaybackFragment.kt`. Update both to:

```
http://YOUR_NAS_IP:8080
```

Then rebuild and install the app:
```bash
cd shield-app
./gradlew installDebug
```

## 8. Verify End-to-End

```bash
# Check backend is running
curl http://your-nas-ip:8080/docs

# Check feeds work
curl http://your-nas-ip:8080/api/feed/home | python -m json.tool

# Check cache status
curl http://your-nas-ip:8080/api/cache/status

# Check a thumbnail loads
curl -I http://your-nas-ip:8080/api/video/dQw4w9WgXcQ/thumbnail
```

On Shield TV: open ShieldTube → browse feeds → play a video → verify HDR passthrough on LG OLED.

## 9. Monitoring

```bash
# Live logs
docker-compose logs -f

# Cache disk usage
curl http://your-nas-ip:8080/api/cache/status

# Check specific video download status
curl http://your-nas-ip:8080/api/video/VIDEO_ID/download-status
```

## 10. Updating

```bash
cd /volume1/shieldtube/app
git pull
docker-compose build
docker-compose up -d
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Container won't start | Port 8080 in use | Check `netstat -tlnp | grep 8080`, change port in compose |
| Permission denied on volumes | DSM permissions | `chown -R 1000:1000 /volume1/shieldtube/cache` |
| FFmpeg OOM killed | Not enough RAM | Set `FFMPEG_THREADS=1`, increase Docker memory limit |
| Videos buffer/stutter | NAS CPU too slow for muxing | Expected for 4K — use 1080p. Or use Lenovo laptop as backend |
| Can't reach from Shield | Firewall blocking | DSM Control Panel → Security → Firewall → allow port 8080 |
| OAuth token expired | Refresh token missing | Re-run device flow or refresh via OAuth Playground |
| "No OAuth token" error | .env not mounted | Verify `env_file` path in docker-compose.yml |
| Database locked | Concurrent access | Shouldn't happen with single user. Restart container |
