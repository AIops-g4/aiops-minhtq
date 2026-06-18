#!/usr/bin/env bash
set -euo pipefail

SERVICE=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service) SERVICE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    *) echo "[clear_cache] ERROR: unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$SERVICE" ]]; then
  echo "[clear_cache] ERROR: --service <name> required"
  exit 1
fi

CONTAINER="ronki-${SERVICE}"

if $DRY_RUN; then
  echo "[DRY-RUN] would execute: docker kill --signal=SIGHUP ${CONTAINER}"
  exit 0
fi

if ! docker inspect "${CONTAINER}" >/dev/null 2>&1; then
  echo "[clear_cache] ERROR: container ${CONTAINER} not found"
  exit 1
fi

docker kill --signal=SIGHUP "${CONTAINER}"
echo "[clear_cache] SIGHUP sent to ${CONTAINER}."
exit 0
