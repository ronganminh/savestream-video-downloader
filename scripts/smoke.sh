#!/usr/bin/env sh
set -eu
BASE_URL="${BASE_URL:-http://127.0.0.1:8787}"
HEADER=""
if [ -n "${INTERNAL_API_KEY:-}" ]; then
  HEADER="X-SaveStream-Service-Key: ${INTERNAL_API_KEY}"
fi
curl -fsS "$BASE_URL/healthz"
printf '\n'
if [ "$#" -gt 0 ]; then
  if [ -n "$HEADER" ]; then
    curl -fsS -X POST "$BASE_URL/v1/resolve" -H "$HEADER" -H 'content-type: application/json' -d "{\"source\":\"tiktok\",\"url\":\"$1\"}"
  else
    curl -fsS -X POST "$BASE_URL/v1/resolve" -H 'content-type: application/json' -d "{\"source\":\"tiktok\",\"url\":\"$1\"}"
  fi
  printf '\n'
fi
