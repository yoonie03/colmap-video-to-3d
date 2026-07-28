#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/install_cuda_toolkit.log"
exec > >(tee "${LOG_FILE}") 2>&1

function info() { printf "[INFO] %s\n" "$*"; }
function warn() { printf "[WARN] %s\n" "$*"; }
function error() { printf "[ERROR] %s\n" "$*"; }

if [[ $(id -u) -ne 0 ]]; then
  warn "This script requires sudo privileges for apt operations. You will be prompted to continue."
fi

if [[ -f /etc/os-release ]]; then
  source /etc/os-release
  if [[ "$ID" != "ubuntu" || "$VERSION_ID" != "24.04" ]]; then
    error "This script is designed for Ubuntu 24.04. Detected ${NAME} ${VERSION_ID}."
    exit 1
  fi
else
  error "/etc/os-release not found. Cannot verify Ubuntu version."
  exit 1
fi

info "Installing CUDA toolkit for Ubuntu 24.04"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update
sudo apt-get install -y --no-install-recommends curl gnupg ca-certificates software-properties-common ffmpeg

REPO_FILE="/etc/apt/sources.list.d/cuda-ubuntu2404-x86_64.list"
if [[ ! -f "$REPO_FILE" ]]; then
  info "Adding NVIDIA CUDA repository"
  sudo rm -f /etc/apt/keyrings/nvidia-archive-keyring.gpg
  sudo apt-get install -y --no-install-recommends nvidia-keyring
  sudo bash -c "cat > '${REPO_FILE}' <<'EOF'

deb [signed-by=/usr/share/keyrings/nvidia-archive-keyring.gpg] https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/ /
EOF
"
fi

sudo apt-get update
CUDA_PKG="cuda-toolkit-12-2"
if ! apt-cache policy "$CUDA_PKG" | grep -q 'Candidate:'; then
  info "cuda-toolkit-12-2 package not available; falling back to cuda-toolkit"
  CUDA_PKG="cuda-toolkit"
fi

info "Installing package: $CUDA_PKG"
sudo apt-get install -y --no-install-recommends "$CUDA_PKG"

if [[ ! -d /usr/local/cuda && -d /usr/local/cuda-12.2 ]]; then
  sudo ln -s /usr/local/cuda-12.2 /usr/local/cuda
  info "Created /usr/local/cuda symlink"
fi

if [[ ! -d /usr/local/cuda ]]; then
  error "/usr/local/cuda not found after installation"
  exit 1
fi

BASHRC="${HOME}/.bashrc"
if ! grep -q 'CUDA_TOOLKIT_SETUP' "$BASHRC"; then
  info "Appending CUDA environment variables to $BASHRC"
  cat >> "$BASHRC" <<'EOF'
# CUDA_TOOLKIT_SETUP
export CUDA_HOME=/usr/local/cuda
export PATH="\$CUDA_HOME/bin:\$PATH"
export LD_LIBRARY_PATH="\$CUDA_HOME/lib64:\$LD_LIBRARY_PATH"
EOF
fi

info "Verifying CUDA toolkit"
if command -v nvcc >/dev/null 2>&1; then
  nvcc --version | head -n 2
else
  warn "nvcc not found after installation"
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,driver_version,compute_cap,memory.total --format=csv,noheader,nounits
else
  warn "nvidia-smi unavailable after CUDA toolkit install"
fi

info "CUDA toolkit installation complete"
printf "Logs written to %s\n" "$LOG_FILE"
