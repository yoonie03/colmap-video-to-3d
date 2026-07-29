#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/run_video_to_3d.log"
exec > >(tee "${LOG_FILE}") 2>&1

function usage() {
  cat <<EOF
Usage: $0 --video VIDEO --project-name NAME --output-root ROOT [options]
Options:
  --video         Input video file
  --project-name  Project name under workspace and result directories
  --output-root   Root directory for video/images/workspace/result
  --fps           Frame extraction FPS (default: 2)
  --frame-step    Extract one frame every N frames
  --max-size      Maximum long edge for extracted images
  --quality       low|medium|high (default: medium)
  --sparse-only   Run only up to sparse reconstruction
  --force         Overwrite existing project output
  --resume        Resume from the last completed stage
  --keep-frames   Keep extracted image frames after pipeline
  --clean-temp    Remove temporary workspace data after pipeline
  --help          Show this help message
EOF
  exit 1
}

VIDEO_PATH=""
PROJECT_NAME=""
OUTPUT_ROOT=""
FPS="2"
FRAME_STEP=""
MAX_SIZE="1920"
QUALITY="medium"
SPARSE_ONLY=0
FORCE=0
RESUME=0
KEEP_FRAMES=0
CLEAN_TEMP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --video) VIDEO_PATH="$2"; shift 2 ;; 
    --project-name) PROJECT_NAME="$2"; shift 2 ;; 
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;; 
    --fps) FPS="$2"; shift 2 ;; 
    --frame-step) FRAME_STEP="$2"; shift 2 ;; 
    --max-size) MAX_SIZE="$2"; shift 2 ;; 
    --quality) QUALITY="$2"; shift 2 ;; 
    --sparse-only) SPARSE_ONLY=1; shift ;; 
    --force) FORCE=1; shift ;; 
    --resume) RESUME=1; shift ;; 
    --keep-frames) KEEP_FRAMES=1; shift ;; 
    --clean-temp) CLEAN_TEMP=1; shift ;; 
    --help) usage ;; 
    *) echo "Unknown option: $1"; usage ;; 
  esac
done

if [[ -z "$VIDEO_PATH" || -z "$PROJECT_NAME" || -z "$OUTPUT_ROOT" ]]; then
  usage
fi
if [[ ! -f "$VIDEO_PATH" ]]; then
  echo "Video file not found: $VIDEO_PATH" >&2
  exit 1
fi

VIDEO_PATH="$(realpath "$VIDEO_PATH")"
OUTPUT_ROOT="$(realpath "$OUTPUT_ROOT")"

VIDEO_DIR="$OUTPUT_ROOT/video"
IMAGES_DIR="$OUTPUT_ROOT/images/$PROJECT_NAME"
WORKSPACE_DIR="$OUTPUT_ROOT/workspace/$PROJECT_NAME"
RESULT_DIR="$OUTPUT_ROOT/result/$PROJECT_NAME"
MARKER_DIR="$WORKSPACE_DIR/.markers"
VIDEO_DEST="$VIDEO_DIR/$(basename "$VIDEO_PATH")"

mkdir -p "$VIDEO_DIR" "$IMAGES_DIR" "$WORKSPACE_DIR" "$RESULT_DIR" "$MARKER_DIR"

if [[ $FORCE -eq 1 ]]; then
  echo "Force mode enabled: removing existing workspace and result markers"
  rm -rf "$WORKSPACE_DIR" "$RESULT_DIR"
  mkdir -p "$IMAGES_DIR" "$WORKSPACE_DIR" "$RESULT_DIR" "$MARKER_DIR"
  if [[ "$VIDEO_PATH" != "$VIDEO_DEST" ]]; then
    cp -f "$VIDEO_PATH" "$VIDEO_DEST"
  else
    echo "Input video already inside output video directory; skipping copy"
  fi
else
  if [[ "$VIDEO_PATH" != "$VIDEO_DEST" ]]; then
    cp -n "$VIDEO_PATH" "$VIDEO_DEST" || true
  fi
fi

function stage_done() {
  [[ -f "$MARKER_DIR/$1" ]]
}
function mark_stage() {
  touch "$MARKER_DIR/$1"
}

info() { printf "[INFO] %s\n" "$*"; }
warn() { printf "[WARN] %s\n" "$*"; }
error() { printf "[ERROR] %s\n" "$*"; }

info "Starting video-to-3D pipeline"
info "Video: $VIDEO_PATH"
info "Project: $PROJECT_NAME"
info "Output root: $OUTPUT_ROOT"

info "Extracting video frames"
bash "$SCRIPT_DIR/extract_video_frames.sh" \
  --video "$VIDEO_PATH" \
  --output-dir "$IMAGES_DIR" \
  --fps "$FPS" \
  $( [[ -n "$FRAME_STEP" ]] && printf '%s\n' "--frame-step $FRAME_STEP" ) \
  --max-size "$MAX_SIZE" \
  --quality "$QUALITY"

FRAME_COUNT=$(find "$IMAGES_DIR" -maxdepth 1 -type f -name 'frame_*.jpg' | wc -l)
if (( FRAME_COUNT < 15 )); then
  warn "Extracted only $FRAME_COUNT frames; COLMAP may struggle with sparse input"
fi

DATABASE_PATH="$WORKSPACE_DIR/database.db"
SPARSE_DIR="$WORKSPACE_DIR/sparse"
DENSE_DIR="$WORKSPACE_DIR/dense"
FUSED_PLY="$DENSE_DIR/fused.ply"
MESH_PLY="$RESULT_DIR/mesh.ply"
POINT_CLOUD="$RESULT_DIR/point_cloud.ply"

if [[ $SPARSE_ONLY -eq 0 ]]; then
  if [[ $RESUME -eq 1 ]] && stage_done "features"; then
    info "Skipping feature extraction (already complete)"
  else
    info "Running COLMAP feature extraction"
    mkdir -p "$WORKSPACE_DIR"
    colmap feature_extractor \
      --database_path "$DATABASE_PATH" \
      --image_path "$IMAGES_DIR" \
      --ImageReader.single_camera 1 \
      --FeatureExtraction.max_image_size "$MAX_SIZE"
    mark_stage "features"
  fi

  if [[ $RESUME -eq 1 ]] && stage_done "matching"; then
    info "Skipping image matching (already complete)"
  else
    info "Running COLMAP matching"
    colmap exhaustive_matcher \
      --database_path "$DATABASE_PATH"
    mark_stage "matching"
  fi

  if [[ $RESUME -eq 1 ]] && stage_done "sparse"; then
    info "Skipping sparse reconstruction (already complete)"
  else
    info "Running COLMAP sparse reconstruction"
    mkdir -p "$SPARSE_DIR"
    colmap mapper \
      --database_path "$DATABASE_PATH" \
      --image_path "$IMAGES_DIR" \
      --output_path "$SPARSE_DIR"
    mark_stage "sparse"
  fi

  if [[ $RESUME -eq 1 ]] && stage_done "dense"; then
    info "Skipping dense reconstruction (already complete)"
  else
    info "Running COLMAP dense reconstruction"
    BEST_SPARSE_MODEL=""
    BEST_REGISTERED_IMAGES=-1
    for MODEL_DIR in "$SPARSE_DIR"/*; do
      [[ -d "$MODEL_DIR" ]] || continue
      REGISTERED_IMAGES="$(
        colmap model_analyzer --path "$MODEL_DIR" 2>&1 |
          awk '/Registered images:/ {print $NF; exit}'
      )"
      [[ "$REGISTERED_IMAGES" =~ ^[0-9]+$ ]] || continue
      if (( REGISTERED_IMAGES > BEST_REGISTERED_IMAGES )); then
        BEST_REGISTERED_IMAGES="$REGISTERED_IMAGES"
        BEST_SPARSE_MODEL="$MODEL_DIR"
      fi
    done
    if [[ -z "$BEST_SPARSE_MODEL" ]]; then
      error "No valid sparse reconstruction was found in $SPARSE_DIR"
      exit 1
    fi
    info "Using largest sparse model: $BEST_SPARSE_MODEL ($BEST_REGISTERED_IMAGES registered images)"
    mkdir -p "$DENSE_DIR"
    colmap image_undistorter \
      --image_path "$IMAGES_DIR" \
      --input_path "$BEST_SPARSE_MODEL" \
      --output_path "$DENSE_DIR" \
      --output_type COLMAP \
      --max_image_size "$MAX_SIZE"
    colmap patch_match_stereo \
      --workspace_path "$DENSE_DIR" \
      --workspace_format COLMAP \
      --PatchMatchStereo.geom_consistency true
    colmap stereo_fusion \
      --workspace_path "$DENSE_DIR" \
      --workspace_format COLMAP \
      --input_type geometric \
      --output_path "$FUSED_PLY"
    mark_stage "dense"
  fi

  info "Generating dense point cloud and Poisson mesh"
  mkdir -p "$RESULT_DIR"
  cp "$FUSED_PLY" "$POINT_CLOUD"
  colmap poisson_mesher \
    --input_path "$FUSED_PLY" \
    --output_path "$MESH_PLY"
fi

if [[ $KEEP_FRAMES -eq 0 ]]; then
  info "Removing extracted frames because --keep-frames was not set"
  rm -rf "$IMAGES_DIR"
fi
if [[ $CLEAN_TEMP -eq 1 ]]; then
  info "Cleaning temporary workspace data"
  rm -rf "$WORKSPACE_DIR"
fi

info "Pipeline finished"
info "Result files in $RESULT_DIR"
printf "Logs written to %s\n" "$LOG_FILE"
