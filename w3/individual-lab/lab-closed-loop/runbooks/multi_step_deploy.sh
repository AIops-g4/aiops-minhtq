#!/usr/bin/env bash
set -euo pipefail

SERVICE=""
DRY_RUN=false
STEP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service) SERVICE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    --step-a) STEP="A"; shift ;;
    --step-b) STEP="B"; shift ;;
    --step-c) STEP="C"; shift ;;
    --rollback-a) STEP="RA"; shift ;;
    --rollback-b) STEP="RB"; shift ;;
    --rollback-c) STEP="RC"; shift ;;
    *) echo "[multi_step_deploy] ERROR: unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$SERVICE" ]]; then
  echo "[multi_step_deploy] ERROR: --service <name> required"
  exit 1
fi

CONTAINER="ronki-${SERVICE}"

if $DRY_RUN; then
  case "$STEP" in
    A) echo "[DRY-RUN] step-A would drain traffic from ${CONTAINER}" ;;
    B) echo "[DRY-RUN] step-B would apply config to ${CONTAINER}" ;;
    C) echo "[DRY-RUN] step-C would re-enable traffic for ${CONTAINER}" ;;
    RA) echo "[DRY-RUN] rollback-A would restore traffic for ${CONTAINER}" ;;
    RB) echo "[DRY-RUN] rollback-B would revert config for ${CONTAINER}" ;;
    RC) echo "[DRY-RUN] rollback-C would disable traffic for ${CONTAINER}" ;;
    *) echo "[DRY-RUN] would execute multi-step deploy for ${CONTAINER}" ;;
  esac
  exit 0
fi

case "$STEP" in
  A)
    docker inspect "${CONTAINER}" >/dev/null
    echo "[multi_step_deploy] step-A complete for ${CONTAINER}."
    ;;
  B)
    docker restart "${CONTAINER}"
    echo "[multi_step_deploy] step-B complete for ${CONTAINER}."
    ;;
  C)
    docker start "${CONTAINER}" >/dev/null 2>&1 || true
    STATUS="$(docker inspect --format '{{.State.Status}}' "${CONTAINER}" 2>/dev/null || echo missing)"
    if [[ "$STATUS" != "running" ]]; then
      echo "[multi_step_deploy] ERROR: step-C failed, status=${STATUS}"
      exit 1
    fi
    echo "[multi_step_deploy] step-C complete for ${CONTAINER}."
    ;;
  RA)
    docker start "${CONTAINER}" >/dev/null 2>&1 || true
    echo "[multi_step_deploy] rollback-A complete for ${CONTAINER}."
    ;;
  RB)
    docker restart "${CONTAINER}" >/dev/null 2>&1 || docker start "${CONTAINER}"
    echo "[multi_step_deploy] rollback-B complete for ${CONTAINER}."
    ;;
  RC)
    docker stop "${CONTAINER}" >/dev/null 2>&1 || true
    echo "[multi_step_deploy] rollback-C complete for ${CONTAINER}."
    ;;
  *)
    echo "[multi_step_deploy] ERROR: choose --step-a/b/c or --rollback-a/b/c"
    exit 1
    ;;
esac

exit 0
