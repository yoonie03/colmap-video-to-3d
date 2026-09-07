#!/usr/bin/env python3
"""Project 2D crack masks onto a COLMAP dense fused point cloud."""

from __future__ import annotations

import argparse
import json
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


VERTEX_DTYPE = np.dtype([
    ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
    ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
    ("red", "u1"), ("green", "u1"), ("blue", "u1"),
])


@dataclass(frozen=True)
class Camera:
    model: str
    width: int
    height: int
    params: tuple[float, ...]


@dataclass(frozen=True)
class ImagePose:
    camera_id: int
    rotation: np.ndarray
    translation: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Color COLMAP dense points using 2D crack masks")
    parser.add_argument("--point-cloud", type=Path, required=True, help="COLMAP fused PLY")
    parser.add_argument("--visibility", type=Path, required=True, help="Matching fused.ply.vis")
    parser.add_argument("--fusion-config", type=Path, required=True, help="COLMAP stereo/fusion.cfg")
    parser.add_argument("--cameras", type=Path, required=True, help="COLMAP cameras.txt")
    parser.add_argument("--images", type=Path, required=True, help="COLMAP images.txt")
    parser.add_argument("--masks-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, help="Projection summary JSON")
    parser.add_argument("--min-views", type=int, default=1, help="Minimum positive mask observations")
    parser.add_argument("--mask-dilation", type=int, default=2, help="Mask expansion radius in pixels")
    parser.add_argument("--red", type=int, default=255)
    parser.add_argument("--green", type=int, default=0)
    parser.add_argument("--blue", type=int, default=0)
    return parser.parse_args()


def read_cameras(path: Path) -> dict[int, Camera]:
    cameras: dict[int, Camera] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        camera_id = int(fields[0])
        cameras[camera_id] = Camera(fields[1], int(fields[2]), int(fields[3]), tuple(map(float, fields[4:])))
    if not cameras:
        raise RuntimeError(f"No cameras found in {path}")
    unsupported = sorted({camera.model for camera in cameras.values()} - {"SIMPLE_RADIAL", "PINHOLE"})
    if unsupported:
        raise RuntimeError(f"Unsupported camera model(s): {', '.join(unsupported)}")
    return cameras


def quaternion_to_rotation(qw: float, qx: float, qy: float, qz: float) -> np.ndarray:
    return np.array([
        [1 - 2 * qy * qy - 2 * qz * qz, 2 * qx * qy - 2 * qz * qw, 2 * qx * qz + 2 * qy * qw],
        [2 * qx * qy + 2 * qz * qw, 1 - 2 * qx * qx - 2 * qz * qz, 2 * qy * qz - 2 * qx * qw],
        [2 * qx * qz - 2 * qy * qw, 2 * qy * qz + 2 * qx * qw, 1 - 2 * qx * qx - 2 * qy * qy],
    ], dtype=np.float64)


def read_images(path: Path) -> dict[str, ImagePose]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    images: dict[str, ImagePose] = {}
    for index in range(0, len(lines), 2):
        fields = lines[index].split()
        if len(fields) < 10:
            raise RuntimeError(f"Malformed image record in {path}: {lines[index]}")
        quaternion = tuple(map(float, fields[1:5]))
        translation = np.array(tuple(map(float, fields[5:8])), dtype=np.float64)
        images[fields[9]] = ImagePose(int(fields[8]), quaternion_to_rotation(*quaternion), translation)
    if not images:
        raise RuntimeError(f"No image poses found in {path}")
    return images


def read_ply(path: Path) -> tuple[bytes, np.ndarray]:
    with path.open("rb") as handle:
        header_lines: list[bytes] = []
        vertex_count = None
        properties: list[bytes] = []
        while True:
            line = handle.readline()
            if not line:
                raise RuntimeError(f"PLY header is incomplete: {path}")
            header_lines.append(line)
            stripped = line.strip()
            if stripped.startswith(b"element vertex "):
                vertex_count = int(stripped.split()[2])
            elif stripped.startswith(b"property "):
                properties.append(stripped)
            elif stripped == b"end_header":
                break
        expected = [
            b"property float x", b"property float y", b"property float z",
            b"property float nx", b"property float ny", b"property float nz",
            b"property uchar red", b"property uchar green", b"property uchar blue",
        ]
        if b"format binary_little_endian 1.0" not in [line.strip() for line in header_lines]:
            raise RuntimeError("Only binary little-endian PLY is supported")
        if vertex_count is None or properties[:9] != expected:
            raise RuntimeError("Unexpected PLY vertex layout")
        vertices = np.fromfile(handle, dtype=VERTEX_DTYPE, count=vertex_count)
    if len(vertices) != vertex_count:
        raise RuntimeError(f"Expected {vertex_count} vertices, read {len(vertices)}")
    return b"".join(header_lines), vertices


def read_visibility(path: Path, expected_points: int, image_count: int) -> list[np.ndarray]:
    buckets: list[list[int]] = [[] for _ in range(image_count)]
    with path.open("rb") as handle:
        raw_count = handle.read(8)
        if len(raw_count) != 8:
            raise RuntimeError(f"Invalid visibility file: {path}")
        point_count = struct.unpack("<Q", raw_count)[0]
        if point_count != expected_points:
            raise RuntimeError(f"Visibility has {point_count} points, PLY has {expected_points}")
        for point_index in range(point_count):
            raw = handle.read(4)
            if len(raw) != 4:
                raise RuntimeError(f"Visibility ended at point {point_index}")
            visible_count = struct.unpack("<I", raw)[0]
            indices_raw = handle.read(visible_count * 4)
            if len(indices_raw) != visible_count * 4:
                raise RuntimeError(f"Visibility list ended at point {point_index}")
            for image_index in struct.unpack(f"<{visible_count}I", indices_raw):
                if image_index >= image_count:
                    raise RuntimeError(f"Visibility image index {image_index} exceeds fusion config")
                buckets[image_index].append(point_index)
    return [np.asarray(bucket, dtype=np.int64) for bucket in buckets]


def project_points(points: np.ndarray, pose: ImagePose, camera: Camera) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xyz = np.column_stack((points["x"], points["y"], points["z"])).astype(np.float64, copy=False)
    camera_xyz = xyz @ pose.rotation.T + pose.translation
    depth = camera_xyz[:, 2]
    safe_depth = np.where(depth > 1e-12, depth, 1.0)
    x = camera_xyz[:, 0] / safe_depth
    y = camera_xyz[:, 1] / safe_depth
    if camera.model == "PINHOLE":
        fx, fy, cx, cy = camera.params
        u = fx * x + cx
        v = fy * y + cy
    elif camera.model == "SIMPLE_RADIAL":
        f, cx, cy, k = camera.params
        factor = 1.0 + k * (x * x + y * y)
        u = f * factor * x + cx
        v = f * factor * y + cy
    else:
        raise RuntimeError(f"Unsupported camera model: {camera.model}")
    return u, v, depth


def main() -> int:
    args = parse_args()
    if args.min_views < 1 or args.mask_dilation < 0:
        raise ValueError("--min-views must be positive and --mask-dilation cannot be negative")
    color = (args.red, args.green, args.blue)
    if any(channel < 0 or channel > 255 for channel in color):
        raise ValueError("Color channels must be between 0 and 255")

    started = time.perf_counter()
    fusion_names = [line.strip() for line in args.fusion_config.read_text(encoding="utf-8").splitlines() if line.strip()]
    cameras = read_cameras(args.cameras)
    poses = read_images(args.images)
    header, vertices = read_ply(args.point_cloud)
    print(f"Points: {len(vertices)}")
    print(f"Fusion images: {len(fusion_names)}")
    visibility = read_visibility(args.visibility, len(vertices), len(fusion_names))

    positive_views = np.zeros(len(vertices), dtype=np.uint16)
    tested_views = np.zeros(len(vertices), dtype=np.uint16)
    frames_used = 0
    candidate_frames = 0
    kernel = None
    if args.mask_dilation:
        size = args.mask_dilation * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))

    for image_index, name in enumerate(fusion_names):
        mask_path = args.masks_dir / f"{Path(name).stem}.png"
        if not mask_path.is_file() or name not in poses:
            continue
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise RuntimeError(f"Could not read mask: {mask_path}")
        pose = poses[name]
        camera = cameras[pose.camera_id]
        if mask.shape != (camera.height, camera.width):
            raise RuntimeError(f"Mask {mask_path.name} is {mask.shape[::-1]}, camera expects {(camera.width, camera.height)}")
        point_indices = visibility[image_index]
        frames_used += 1
        if len(point_indices) == 0:
            continue
        if np.any(mask):
            candidate_frames += 1
            if kernel is not None:
                mask = cv2.dilate(mask, kernel)
        u, v, depth = project_points(vertices[point_indices], pose, camera)
        ui = np.rint(u).astype(np.int64)
        vi = np.rint(v).astype(np.int64)
        valid = (depth > 0) & (ui >= 0) & (ui < camera.width) & (vi >= 0) & (vi < camera.height)
        valid_points = point_indices[valid]
        tested_views[valid_points] += 1
        if np.any(mask) and len(valid_points):
            hits = mask[vi[valid], ui[valid]] > 0
            positive_views[valid_points[hits]] += 1
        if (image_index + 1) % 10 == 0 or image_index + 1 == len(fusion_names):
            print(f"[{image_index + 1:03d}/{len(fusion_names):03d}] {name}")

    crack_points = positive_views >= args.min_views
    vertices["red"][crack_points] = args.red
    vertices["green"][crack_points] = args.green
    vertices["blue"][crack_points] = args.blue
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as handle:
        handle.write(header)
        vertices.tofile(handle)

    summary = {
        "input_point_cloud": str(args.point_cloud.resolve()),
        "output_point_cloud": str(args.output.resolve()),
        "point_count": len(vertices),
        "crack_point_count": int(np.count_nonzero(crack_points)),
        "crack_point_ratio": float(np.mean(crack_points)),
        "frames_in_fusion_config": len(fusion_names),
        "frames_with_masks": frames_used,
        "frames_with_2d_candidates": candidate_frames,
        "min_views": args.min_views,
        "mask_dilation": args.mask_dilation,
        "color_rgb": list(color),
        "elapsed_seconds": time.perf_counter() - started,
    }
    summary_path = args.summary or args.output.with_suffix(".json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, RuntimeError, ValueError, struct.error) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
