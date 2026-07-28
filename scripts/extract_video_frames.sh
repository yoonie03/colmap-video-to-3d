#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/extract_video_frames.log"
exec > >(tee "${LOG_FILE}") 2>&1

function usage() {
  cat <<EOF
Usage: $0 --video VIDEO_PATH --output-dir OUTPUT_DIR [options]
Options:
  --video         Video input file
  --output-dir    Output directory for extracted frames
  --fps           Frame extraction rate in fps
  --frame-step    Extract one frame every N frames
  --max-size      Maximum long edge in pixels for output images
  --quality       low|medium|high
  --keep-frames   Keep extracted frames if cleanup runs later
  --help          Show this help message
EOF
  exit 1
}

VIDEO_PATH=""
OUTPUT_DIR=""
FPS=""
FRAME_STEP=""
MAX_SIZE=""
QUALITY="medium"
KEEP_FRAMES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --video) VIDEO_PATH="$2"; shift 2 ;; 
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;; 
    --fps) FPS="$2"; shift 2 ;; 
    --frame-step) FRAME_STEP="$2"; shift 2 ;; 
    --max-size) MAX_SIZE="$2"; shift 2 ;; 
    --quality) QUALITY="$2"; shift 2 ;; 
    --keep-frames) KEEP_FRAMES=1; shift ;; 
    --help) usage ;; 
    *) echo "Unknown option: $1"; usage ;; 
  esac
done

if [[ -z "$VIDEO_PATH" || -z "$OUTPUT_DIR" ]]; then
  usage
fi
if [[ ! -f "$VIDEO_PATH" ]]; then
  echo "Video file not found: $VIDEO_PATH" >&2
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required but not installed" >&2
  exit 1
fi
if ! command -v ffprobe >/dev/null 2>&1; then
  echo "ffprobe is required but not installed" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

info() { printf "[INFO] %s\n" "$*"; }

info "Reading video metadata"
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,duration,nb_frames -of default=noprint_wrappers=1:nokey=1 "$VIDEO_PATH"

VIDEO_FPS=""
VIDEO_FPS=$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 "$VIDEO_PATH")
VIDEO_DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$VIDEO_PATH")
info "Video FPS: $VIDEO_FPS"
info "Video duration: ${VIDEO_DURATION}s"

FFMPEG_FILTERS=()
if [[ -n "$FPS" ]]; then
  FFMPEG_FILTERS+=("fps=$FPS")
fi
if [[ -n "$FRAME_STEP" ]]; then
  FFMPEG_FILTERS+=("select='not(mod(n,$FRAME_STEP))',setpts=N/FRAME_RATE/TB")
fi
if [[ -n "$MAX_SIZE" ]]; then
  FFMPEG_FILTERS+=("scale='if(gt(iw,ih),$MAX_SIZE,-1):if(gt(iw,ih),-1,$MAX_SIZE)'")
fi

case "$QUALITY" in
  low) QVAL=8 ;; 
  medium) QVAL=4 ;; 
  high) QVAL=2 ;; 
  *) QVAL=4 ;; 
esac

FILTER_ARG=""
if [[ ${#FFMPEG_FILTERS[@]} -gt 0 ]]; then
  FILTER_ARG="-vf $(IFS=,; echo "${FFMPEG_FILTERS[*]}")"
fi

info "Extracting frames to $OUTPUT_DIR"
set -x
ffmpeg -y -hide_banner -loglevel info -i "$VIDEO_PATH" $FILTER_ARG -qscale:v "$QVAL" "$OUTPUT_DIR/frame_%06d.jpg"
set +x

FRAME_COUNT=$(find "$OUTPUT_DIR" -maxdepth 1 -type f -name 'frame_*.jpg' | wc -l)
info "Extracted frame count: $FRAME_COUNT"
if (( FRAME_COUNT < 10 )); then
  warn "Very few frames were extracted. Adjust fps/frame-step settings."
elif (( FRAME_COUNT > 5000 )); then
  warn "A large number of frames were extracted. Consider lowering fps or increasing frame-step."
fi

QUALITY_REPORT="${OUTPUT_DIR}/frame_quality_report.txt"
if command -v python3 >/dev/null 2>&1 && [[ -f "${SCRIPT_DIR}/frame_quality_check.py" ]]; then
  python3 "${SCRIPT_DIR}/frame_quality_check.py" --frames "$OUTPUT_DIR" --report "$QUALITY_REPORT" || true
  info "Frame quality report: $QUALITY_REPORT"
else
  warn "Python quality check skipped because python3 or helper script is unavailable"
fi

info "Frame extraction complete"
printf "Logs written to %s\n" "$LOG_FILE"
