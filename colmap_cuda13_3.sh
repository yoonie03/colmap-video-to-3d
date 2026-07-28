#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_PATH="$(readlink -f -- "${BASH_SOURCE[0]}")"
readonly PROJECT_DIR="$(cd -- "$(dirname -- "${SCRIPT_PATH}")" && pwd)"
readonly COMPAT_DIR="${PROJECT_DIR}/.local/cuda-compat-13-3/usr/local/cuda-13.3/compat"
readonly COLMAP_BIN="/home/yoonie/Developer/tools/colmap/build/src/colmap/exe/colmap"

if [[ ! -x "${COLMAP_BIN}" ]]; then
  echo "COLMAP build not found: ${COLMAP_BIN}" >&2
  exit 1
fi

if [[ ! -f "${COMPAT_DIR}/libcuda.so.1" ]]; then
  echo "CUDA 13.3 compatibility libraries not found: ${COMPAT_DIR}" >&2
  exit 1
fi

export LD_LIBRARY_PATH="${COMPAT_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
exec "${COLMAP_BIN}" "$@"
