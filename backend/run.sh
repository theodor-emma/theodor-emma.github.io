#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

usage() {
    cat <<'EOF'
Usage: run.sh [options]

Options:
  --reload    Enable uvicorn auto-reload on file changes (development)
  --public    Bind to 0.0.0.0 (reachable from other machines) instead of 127.0.0.1
  --help      Show this help message and exit
EOF
}

RELOAD=""
HOST="127.0.0.1"
for arg in "$@"; do
    case "$arg" in
        --reload) RELOAD="--reload" ;;
        --public) HOST="0.0.0.0" ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown argument: $arg" >&2; usage >&2; exit 1 ;;
    esac
done

echo "Syncing dependencies…"
uv sync --no-dev

echo "Starting uvicorn on ${HOST}:8000…"
exec uv run uvicorn main:app \
    --host "$HOST" \
    --port 8000 \
    --proxy-headers \
    --forwarded-allow-ips="127.0.0.1" \
    $RELOAD
