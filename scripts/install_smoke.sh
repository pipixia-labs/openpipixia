#!/usr/bin/env bash
set -euo pipefail

# Lightweight end-to-end smoke for install + doctor (+ optional gateway probe).
# Usage:
#   scripts/install_smoke.sh
#   scripts/install_smoke.sh --force
#   scripts/install_smoke.sh --with-gateway

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

FORCE_FLAG=""
WITH_GATEWAY=0

while (($# > 0)); do
  case "$1" in
    --force)
      FORCE_FLAG="--force"
      shift
      ;;
    --with-gateway)
      WITH_GATEWAY=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if ! command -v openheron >/dev/null 2>&1; then
  echo "openheron command not found. Activate venv and run 'pip install -e .' first." >&2
  exit 1
fi

echo "[smoke] running install --non-interactive ${FORCE_FLAG}"
openheron install --non-interactive ${FORCE_FLAG}

echo "[smoke] running doctor"
openheron doctor

if [[ "${WITH_GATEWAY}" == "1" ]]; then
  echo "[smoke] running gateway probe"
  if command -v timeout >/dev/null 2>&1; then
    timeout 5s openheron gateway --channels local || true
  else
    echo "[smoke] 'timeout' not found, skipping gateway probe"
  fi
fi

echo "[smoke] done"
