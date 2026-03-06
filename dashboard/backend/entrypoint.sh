#!/bin/sh
set -e

# Auto-create tables if they don't exist (for demo/dev)
python -c "
import asyncio
from app.database import engine, Base
import app.models

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

asyncio.run(init_db())
print('Database tables ready.')
"

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
