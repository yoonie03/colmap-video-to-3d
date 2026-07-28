#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/install_colmap_cuda.log"
exec > >(tee "${LOG_FILE}") 2>&1

function info() { printf "[INFO] %s\n" "$*"; }
function warn() { printf "[WARN] %s\n" "$*"; }
function error() { printf "[ERROR] %s\n" "$*"; }

TOOLS_ROOT="${HOME}/Developer/tools/colmap"
SRC_DIR="${TOOLS_ROOT}/src"
BUILD_DIR="${TOOLS_ROOT}/build"
INSTALL_PREFIX="/usr/local"

if [[ -f /etc/os-release ]]; then
  source /etc/os-release
  if [[ "$ID" != "ubuntu" ]]; then
    warn "This script is designed for Ubuntu but detected $NAME. Continuing with caution."
  fi
fi

info "Installing COLMAP CUDA build prerequisites"
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  build-essential cmake ninja-build git \
  libboost-program-options-dev libboost-system-dev libboost-filesystem-dev libboost-graph-dev \
  libeigen3-dev libflann-dev libsuitesparse-dev libfreeimage-dev \
  libgoogle-glog-dev libgflags-dev libglew-dev libqt5opengl5-dev libqt5svg5-dev qtbase5-dev \
  libatlas-base-dev liblapack-dev libblas-dev libcgal-dev libmetis-dev libopencv-dev \
  libprotobuf-dev protobuf-compiler libsqlite3-dev libjpeg-dev libpng-dev libtiff-dev \
  libglu1-mesa-dev libopenimageio-dev openimageio-tools libceres-dev

mkdir -p "$SRC_DIR" "$BUILD_DIR"

if [[ ! -d "$SRC_DIR/.git" ]]; then
  info "Cloning COLMAP repository"
  git clone --depth 1 https://github.com/colmap/colmap.git "$SRC_DIR"
else
  info "COLMAP source already exists; pulling latest changes"
  git -C "$SRC_DIR" pull --ff-only || true
fi

CUDA_ARCH_BIN="86"
if command -v nvidia-smi >/dev/null 2>&1; then
  local_compute_cap=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader,nounits 2>/dev/null | head -n1 || true)
  if [[ "$local_compute_cap" =~ ^([0-9]+)\.([0-9]+)$ ]]; then
    CUDA_ARCH_BIN="${BASH_REMATCH[1]}${BASH_REMATCH[2]}"
  fi
fi
info "Using CUDA_ARCH_BIN=${CUDA_ARCH_BIN}"

info "Configuring COLMAP build"
cmake -S "$SRC_DIR" -B "$BUILD_DIR" \
  -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$INSTALL_PREFIX" \
  -DCUDA_ENABLED=ON \
  -DCUDA_ARCH_BIN="$CUDA_ARCH_BIN" \
  -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/gcc-13 \
  -DCMAKE_CUDA_ARCHITECTURES=90-virtual \
  -DBUILD_GUI=ON \
  -DBUILD_TESTS=OFF

info "Building COLMAP"
ninja -C "$BUILD_DIR"

info "Installing COLMAP"
sudo ninja -C "$BUILD_DIR" install

info "Verifying COLMAP installation"
if command -v colmap >/dev/null 2>&1; then
  colmap -h | head -n 20
  if colmap -h 2>&1 | grep -iq "gpu\|cuda\|gpu-index"; then
    info "COLMAP reports CUDA/GPU options"
  else
    warn "COLMAP help output does not clearly show CUDA support"
  fi
else
  error "colmap command not found after installation"
  exit 1
fi

if [[ -n "${DISPLAY-}" ]]; then
  if colmap gui --help >/dev/null 2>&1; then
    info "COLMAP GUI command checked successfully"
  else
    warn "COLMAP GUI command did not return success in this environment"
  fi
else
  warn "DISPLAY is not set; GUI launch check was skipped"
fi

info "COLMAP CUDA build complete"
printf "Logs written to %s\n" "$LOG_FILE"
