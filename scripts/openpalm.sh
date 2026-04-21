#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"

if [ ! -x "${VENV_PYTHON}" ]; then
  echo "[error] Virtual environment not found. Run: ${PROJECT_ROOT}/scripts/install_macos.sh"
  exit 1
fi

export DYLD_LIBRARY_PATH="/opt/homebrew/lib:${DYLD_LIBRARY_PATH:-}"
exec "${VENV_PYTHON}" -m openpalm "$@"
