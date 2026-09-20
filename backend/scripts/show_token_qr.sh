#!/bin/sh
set -eu

if ! command -v qrencode >/dev/null 2>&1; then
  echo "qrencode is required (Debian: apt install qrencode)" >&2
  exit 1
fi

if [ -z "${VINTRADAR_API_TOKEN:-}" ] && [ -f /app/.env ]; then
  VINTRADAR_API_TOKEN="$(sed -n 's/^VINTRADAR_API_TOKEN=//p' /app/.env | tail -n 1)"
fi

if [ -z "${VINTRADAR_API_TOKEN:-}" ]; then
  echo "Set VINTRADAR_API_TOKEN or mount .env at /app/.env" >&2
  exit 1
fi

printf '%s' "$VINTRADAR_API_TOKEN" | qrencode -t ANSIUTF8
