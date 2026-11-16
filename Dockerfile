# syntax=docker/dockerfile:1

FROM node:22-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DB_PATH=/data/music-scrap.db \
    BACKUP_DIR=/backups \
    FRONTEND_DIST=/app/frontend/dist

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg chromaprint-tools curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/pyproject.toml ./pyproject.toml
COPY backend/app ./app
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
RUN pip install --no-cache-dir .

COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin app \
 && mkdir -p /data /backups \
 && chown -R app:app /app /data /backups

USER app
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/api/health || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8080"]
