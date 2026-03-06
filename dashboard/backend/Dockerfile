FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install evalcraft SDK first
COPY pyproject.toml /sdk/pyproject.toml
COPY evalcraft /sdk/evalcraft
COPY README.md /sdk/README.md
RUN pip install --no-cache-dir /sdk

COPY dashboard/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dashboard/backend/ .
RUN chmod +x entrypoint.sh

ENV PYTHONPATH=/app
EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
