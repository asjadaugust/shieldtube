FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg openssl nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend into /app/backend/ so module path backend.api.main works
COPY requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt && \
    pip install --force-reinstall --no-cache-dir yt-dlp

COPY . ./backend/

EXPOSE 9443 8080
CMD ["sh", "/app/backend/start.sh"]
