#!/bin/sh
set -e
cd /app

alembic upgrade head
echo "Database migrations applied."

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 30
