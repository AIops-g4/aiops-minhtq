#!/usr/bin/env bash
set -euo pipefail

SERVICE=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service) SERVICE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    *) echo "[restart_service] ERROR: unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$SERVICE" ]]; then
  echo "[restart_service] ERROR: --service <name> required"
  exit 1
fi

CONTAINER="ronki-${SERVICE}"

if $DRY_RUN; then
  echo "[DRY-RUN] would execute: docker restart ${CONTAINER}"
  exit 0
fi

echo "[restart_service] Restarting ${CONTAINER}..."
if docker inspect "${CONTAINER}" >/dev/null 2>&1; then
  docker restart "${CONTAINER}"
else
  echo "[restart_service] ERROR: container ${CONTAINER} not found"
  exit 1
fi

sleep 5
STATUS="$(docker inspect --format '{{.State.Status}}' "${CONTAINER}" 2>/dev/null || echo missing)"
if [[ "$STATUS" == "running" ]]; then
  echo "[restart_service] ${CONTAINER} is running."
  exit 0
fi

echo "[restart_service] ERROR: ${CONTAINER} status=${STATUS}"
exit 1
