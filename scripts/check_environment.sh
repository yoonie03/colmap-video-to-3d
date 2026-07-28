#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/check_environment.log"
exec > >(tee "${LOG_FILE}") 2>&1

function info() { printf "[INFO] %s\n" "$*"; }
function warn() { printf "[WARN] %s\n" "$*"; }
function error() { printf "[ERROR] %s\n" "$*"; }

function check_cmd() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    printf "%-24s : OK\n" "$cmd"
  else
    printf "%-24s : MISSING\n" "$cmd"
  fi
}

function check_cuda_arch() {
  if command -v nvidia-smi >/dev/null 2>&1; then
    local compute_cap
    compute_cap=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader,nounits 2>/dev/null | head -n1 || true)
    if [[ -n "$compute_cap" ]]; then
      printf "%s\n" "$compute_cap"
      return 0
    fi
  fi
  return 1
}

info "Starting environment check"

info "OS information"
if [[ -f /etc/os-release ]]; then
  source /etc/os-release
  printf "NAME=%s\nVERSION=%s\nID=%s\nVERSION_ID=%s\n" "$NAME" "$VERSION" "$ID" "$VERSION_ID"
else
  warn "/etc/os-release not found"
fi
uname -m

info "CPU architecture"
uname -p || true

info "GPU and NVIDIA driver"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,driver_version,compute_cap,memory.total --format=csv,noheader,nounits
else
  warn "nvidia-smi not found or NVIDIA driver unavailable"
fi

info "Command availability"
check_cmd nvidia-smi
check_cmd nvcc
check_cmd cmake
check_cmd ninja
check_cmd gcc
check_cmd g++
check_cmd ffmpeg
check_cmd ffprobe
check_cmd git
check_cmd colmap

info "CUDA toolkit and GPU"
if command -v nvcc >/dev/null 2>&1; then
  nvcc --version | tail -n 2
  if [[ -L /usr/local/cuda ]] || [[ -d /usr/local/cuda ]]; then
    printf "/usr/local/cuda -> %s\n" "$(readlink -f /usr/local/cuda)"
  fi
else
  warn "nvcc not installed"
fi

info "CMake version"
if command -v cmake >/dev/null 2>&1; then
  cmake --version | head -n1
fi

info "Ninja version"
if command -v ninja >/dev/null 2>&1; then
  ninja --version
fi

info "GCC/G++ version"
if command -v gcc >/dev/null 2>&1; then
  gcc --version | head -n1
fi
if command -v g++ >/dev/null 2>&1; then
  g++ --version | head -n1
fi

info "FFmpeg version"
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -version | head -n1
fi

info "COLMAP check"
if command -v colmap >/dev/null 2>&1; then
  colmap -h 2>/dev/null | head -n 20
  if colmap -h 2>&1 | grep -iq "cuda\|gpu\|gpu-index"; then
    info "COLMAP help output mentions CUDA/GPU options"
  else
    warn "COLMAP help output does not clearly mention CUDA/GPU options"
  fi
else
  warn "COLMAP command not found"
fi

info "Disk space"
df -h . | awk 'NR==2 {print $4 " free on " $6}'

info "GPU memory"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader,nounits
fi

info "CUDA compute capability"
if compute_cap=$(check_cuda_arch); then
  printf "Detected compute capability: %s\n" "$compute_cap"
else
  warn "Unable to detect compute capability via nvidia-smi"
fi

info "Environment check complete"
printf "Logs written to %s\n" "$LOG_FILE"
