#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
BIN_DIR="${HOME}/.local/bin"
LAUNCHER_PATH="${BIN_DIR}/openpalm"
WRAPPER_SOURCE="${PROJECT_ROOT}/scripts/openpalm.sh"

echo "[openpalm] Installing system dependencies..."
if ! command -v brew >/dev/null 2>&1; then
  echo "[error] Homebrew not found. Install it from https://brew.sh and run again."
  exit 1
fi

brew list libmagic >/dev/null 2>&1 || brew install libmagic

echo "[openpalm] Creating virtual environment..."
if [ ! -d "${VENV_DIR}" ]; then
  python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip

echo "[openpalm] Installing OpenPalm package..."
python -m pip install -e "${PROJECT_ROOT}[dev]"

echo "[openpalm] Creating global launcher at ${LAUNCHER_PATH}..."
mkdir -p "${BIN_DIR}"
cat > "${LAUNCHER_PATH}" <<EOF
#!/usr/bin/env bash
exec "${WRAPPER_SOURCE}" "\$@"
EOF
chmod +x "${LAUNCHER_PATH}"

if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
  echo "[warning] ${BIN_DIR} is not in PATH."
  echo "Add this to your ~/.zshrc:"
  echo "export PATH=\"${BIN_DIR}:\$PATH\""
fi

echo
echo "[ok] Installation complete."
echo "Next commands:"
echo "  openpalm status"
echo "  openpalm login"
echo "  openpalm run"
