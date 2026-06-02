# CannEx Webchat — production image
# Build context: repo root (one level up from this file)
# Build:  docker compose -f deploy/docker-compose.yaml build
FROM python:3.11-slim

# System deps:
#   - curl/gnupg/ca-certificates: NodeSource setup
#   - build-essential: bcrypt wheel fallback
#   - git: codegraph npm package may need git for some optional deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg build-essential git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# codegraph CLI — required for L1-L4 code-graph APIs. L0 still works without it.
RUN npm install -g @colbymchenry/codegraph@latest \
    && npm cache clean --force

WORKDIR /app

# Python deps first (cache layer)
COPY webchat/cannex_chat/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Project code. Keep this lean — workspace/ is mounted at runtime as a volume.
COPY lib /app/lib
COPY skills /app/skills
COPY webchat/cannex_chat /app/webchat/cannex_chat
COPY webchat/__init__.py /app/webchat/__init__.py
COPY deploy/seed_users.py /app/deploy/seed_users.py

# Runtime config
ENV CANNEX_ROOT=/app \
    CANNEX_LOGS_DIR=/app/logs \
    CANNEX_USERS_DB=/data/cannex.db \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/lib

# Chainlit listens on 8000 inside the container; only Caddy exposes externally.
EXPOSE 8000

WORKDIR /app/webchat/cannex_chat

# --headless: no browser auto-open. --host 0.0.0.0: listen on all interfaces (Caddy will reach via internal network).
CMD ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "8000", "--headless"]
