# Stage 1: Build
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install evalcraft SDK first
COPY pyproject.toml /sdk/pyproject.toml
COPY evalcraft /sdk/evalcraft
COPY README.md /sdk/README.md
RUN pip install --no-cache-dir --prefix=/install /sdk

COPY dashboard/backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim

RUN groupadd -r evalcraft && useradd -r -g evalcraft -d /app -s /sbin/nologin evalcraft

WORKDIR /app

COPY --from=builder /install /usr/local
COPY dashboard/backend/ .
RUN chmod +x entrypoint.sh

ENV PYTHONPATH=/app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

USER evalcraft

STOPSIGNAL SIGTERM
ENTRYPOINT ["./entrypoint.sh"]
