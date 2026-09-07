#!/usr/bin/env python3
"""Run pretrained crack segmentation on a frame directory or video."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
import torch

from models import UNet


MODEL_SOURCE = "https://github.com/yakhyo/crack-segmentation"
EXPECTED_DICE_SHA256 = "3216b12e9f73b9df08db4788358704a6353c3d0dbc120709054c02529133e14a"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


@dataclass
class FrameResult:
    frame: str
    crack_pixels: int
    crack_ratio: float
    components: int
    max_probability: float
    mean_probability: float
    inference_seconds: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pretrained crack segmentation pipeline")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--frames-dir", type=Path, help="Directory containing input frames")
    source.add_argument("--video", type=Path, help="Video to extract and process")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--weights", type=Path, default=Path(__file__).parent / "weights" / "dice.pt")
    parser.add_argument("--fps", type=float, default=2.0, help="Output/extraction FPS")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--tile-size", type=int, default=512)
    parser.add_argument("--overlap", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--min-area", type=int, default=20, help="Remove connected components smaller than this")
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--overlay-alpha", type=float, default=0.65)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--limit", type=int, help="Process only the first N frames (smoke tests)")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_device(requested: str) -> torch.device:
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("--device cuda was requested, but PyTorch cannot access CUDA")
    use_cuda = requested == "cuda" or (requested == "auto" and torch.cuda.is_available())
    return torch.device("cuda" if use_cuda else "cpu")


def load_model(weights: Path, device: torch.device) -> UNet:
    if not weights.is_file():
        raise FileNotFoundError(f"Weights not found: {weights}")
    # This release stores a full model object inside its checkpoint. Only load
    # checkpoints obtained from the pinned upstream release/checksum.
    checkpoint = torch.load(weights, map_location="cpu", weights_only=False)
    state = checkpoint.get("model", checkpoint)
    if hasattr(state, "state_dict"):
        state = state.float().state_dict()
    model = UNet(in_channels=3, out_channels=2)
    model.load_state_dict(state)
    model.eval().to(device)
    return model


def positions(length: int, tile: int, overlap: int) -> list[int]:
    if length <= tile:
        return [0]
    stride = tile - overlap
    values = list(range(0, length - tile + 1, stride))
    if values[-1] != length - tile:
        values.append(length - tile)
    return values


def pad_image(image: np.ndarray, tile_size: int) -> tuple[np.ndarray, tuple[int, int]]:
    height, width = image.shape[:2]
    pad_bottom = max(0, tile_size - height)
    pad_right = max(0, tile_size - width)
    if pad_bottom or pad_right:
        image = cv2.copyMakeBorder(image, 0, pad_bottom, 0, pad_right, cv2.BORDER_REFLECT_101)
    return image, (height, width)


def infer_probability(
    model: UNet,
    image_bgr: np.ndarray,
    device: torch.device,
    tile_size: int,
    overlap: int,
    batch_size: int,
) -> np.ndarray:
    padded, original_shape = pad_image(image_bgr, tile_size)
    height, width = padded.shape[:2]
    coords = [(y, x) for y in positions(height, tile_size, overlap) for x in positions(width, tile_size, overlap)]
    probability_sum = np.zeros((height, width), dtype=np.float32)
    coverage = np.zeros((height, width), dtype=np.float32)

    for start in range(0, len(coords), batch_size):
        batch_coords = coords[start : start + batch_size]
        tiles = [padded[y : y + tile_size, x : x + tile_size] for y, x in batch_coords]
        rgb = np.stack([cv2.cvtColor(tile, cv2.COLOR_BGR2RGB) for tile in tiles])
        tensor = torch.from_numpy(rgb.transpose(0, 3, 1, 2)).float().div_(255.0).to(device)
        with torch.inference_mode():
            if device.type == "cuda":
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    logits = model(tensor)
            else:
                logits = model(tensor)
            probabilities = torch.softmax(logits.float(), dim=1)[:, 1].cpu().numpy()
        for (y, x), probability in zip(batch_coords, probabilities):
            probability_sum[y : y + tile_size, x : x + tile_size] += probability
            coverage[y : y + tile_size, x : x + tile_size] += 1.0

    original_height, original_width = original_shape
    return (probability_sum / np.maximum(coverage, 1.0))[:original_height, :original_width]


def clean_mask(probability: np.ndarray, threshold: float, min_area: int) -> tuple[np.ndarray, int]:
    mask = (probability >= threshold).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    clean = np.zeros_like(mask)
    kept = 0
    for label in range(1, count):
        if int(stats[label, cv2.CC_STAT_AREA]) >= min_area:
            clean[labels == label] = 255
            kept += 1
    return clean, kept


def make_overlay(image: np.ndarray, probability: np.ndarray, mask: np.ndarray, alpha: float) -> np.ndarray:
    overlay = image.copy()
    crack = mask > 0
    confidence = probability[crack, None]
    red = np.zeros((int(crack.sum()), 3), dtype=np.float32)
    red[:, 2] = 255.0
    source = overlay[crack].astype(np.float32)
    local_alpha = np.clip(alpha * (0.5 + confidence), 0.0, 1.0)
    overlay[crack] = (source * (1.0 - local_alpha) + red * local_alpha).astype(np.uint8)
    return overlay


def prepare_output(output_dir: Path, overwrite: bool) -> dict[str, Path]:
    if output_dir.exists() and any(output_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(f"Output is not empty: {output_dir}; pass --overwrite to replace it")
        shutil.rmtree(output_dir)
    paths = {name: output_dir / name for name in ("frames", "masks", "probability_maps", "overlays")}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def extract_video(video: Path, frames_dir: Path, fps: float) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required for --video")
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video),
        "-vf", f"fps={fps}", "-qscale:v", "2", str(frames_dir / "frame_%06d.jpg"),
    ]
    subprocess.run(command, check=True)


def frame_paths(frames_dir: Path, limit: int | None) -> list[Path]:
    frames = sorted(path for path in frames_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)
    if limit is not None:
        frames = frames[:limit]
    if not frames:
        raise RuntimeError(f"No image frames found in {frames_dir}")
    return frames


def write_video(overlays: list[Path], output: Path, fps: float) -> None:
    if shutil.which("ffmpeg") is not None:
        command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", str(fps), "-pattern_type", "glob", "-i", str(overlays[0].parent / "*.png"),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(output),
        ]
        subprocess.run(command, check=True)
        return
    first = cv2.imread(str(overlays[0]))
    height, width = first.shape[:2]
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Could not create video: {output}")
    try:
        for path in overlays:
            frame = cv2.imread(str(path))
            if frame is None or frame.shape[:2] != (height, width):
                raise RuntimeError(f"Invalid or inconsistent overlay frame: {path}")
            writer.write(frame)
    finally:
        writer.release()


def main() -> int:
    args = parse_args()
    if not 0.0 < args.threshold < 1.0:
        raise ValueError("--threshold must be between 0 and 1")
    if args.tile_size < 32 or args.tile_size % 16:
        raise ValueError("--tile-size must be >= 32 and divisible by 16")
    if not 0 <= args.overlap < args.tile_size:
        raise ValueError("--overlap must be >= 0 and less than --tile-size")
    if args.batch_size < 1 or args.min_area < 0 or args.fps <= 0:
        raise ValueError("--batch-size and --fps must be positive; --min-area cannot be negative")

    paths = prepare_output(args.output_dir.resolve(), args.overwrite)
    if args.video:
        extract_video(args.video.resolve(), paths["frames"], args.fps)
        input_dir = paths["frames"]
    else:
        input_dir = args.frames_dir.resolve()
    frames = frame_paths(input_dir, args.limit)

    device = select_device(args.device)
    weights_hash = sha256(args.weights.resolve())
    if args.weights.name == "dice.pt" and weights_hash != EXPECTED_DICE_SHA256:
        raise RuntimeError("dice.pt checksum does not match the pinned upstream release")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"Frames: {len(frames)}")
    model = load_model(args.weights.resolve(), device)

    results: list[FrameResult] = []
    overlays: list[Path] = []
    pipeline_start = time.perf_counter()
    for index, frame_path in enumerate(frames, start=1):
        image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"Could not read frame: {frame_path}")
        started = time.perf_counter()
        probability = infer_probability(model, image, device, args.tile_size, args.overlap, args.batch_size)
        mask, components = clean_mask(probability, args.threshold, args.min_area)
        elapsed = time.perf_counter() - started

        name = frame_path.stem + ".png"
        probability_path = paths["probability_maps"] / name
        mask_path = paths["masks"] / name
        overlay_path = paths["overlays"] / name
        cv2.imwrite(str(probability_path), np.round(probability * 255.0).astype(np.uint8))
        cv2.imwrite(str(mask_path), mask)
        cv2.imwrite(str(overlay_path), make_overlay(image, probability, mask, args.overlay_alpha))
        overlays.append(overlay_path)

        crack_pixels = int(np.count_nonzero(mask))
        results.append(FrameResult(
            frame=frame_path.name,
            crack_pixels=crack_pixels,
            crack_ratio=crack_pixels / mask.size,
            components=components,
            max_probability=float(probability.max()),
            mean_probability=float(probability.mean()),
            inference_seconds=elapsed,
        ))
        print(f"[{index:03d}/{len(frames):03d}] {frame_path.name}: {components} components, {crack_pixels} px, {elapsed:.2f}s")

    video_path = args.output_dir.resolve() / "crack_overlay.mp4"
    write_video(overlays, video_path, args.fps)
    total_seconds = time.perf_counter() - pipeline_start
    summary = {
        "model": {"source": MODEL_SOURCE, "weights": str(args.weights.resolve()), "sha256": weights_hash},
        "runtime": {
            "device": str(device),
            "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else None,
            "torch": torch.__version__,
            "total_seconds": total_seconds,
        },
        "settings": {
            "threshold": args.threshold,
            "tile_size": args.tile_size,
            "overlap": args.overlap,
            "batch_size": args.batch_size,
            "min_area": args.min_area,
            "fps": args.fps,
        },
        "aggregate": {
            "frame_count": len(results),
            "frames_with_candidates": sum(result.crack_pixels > 0 for result in results),
            "total_crack_pixels": sum(result.crack_pixels for result in results),
            "mean_crack_ratio": sum(result.crack_ratio for result in results) / len(results),
        },
        "frames": [asdict(result) for result in results],
    }
    with (args.output_dir.resolve() / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
    with (args.output_dir.resolve() / "frames.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FrameResult.__dataclass_fields__.keys())
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)
    print(f"Done: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
