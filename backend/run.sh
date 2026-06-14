#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Syncing dependencies…"
uv sync

echo "Starting uvicorn on 127.0.0.1:8000…"
exec uv run uvicorn main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --proxy-headers \
    --forwarded-allow-ips="127.0.0.1"
