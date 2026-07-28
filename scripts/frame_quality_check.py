#!/usr/bin/env python3
import argparse
import os
import cv2
import numpy as np
from pathlib import Path

HASH_SIZE = 8


def dhash(image, hash_size=HASH_SIZE):
    resized = cv2.resize(image, (hash_size + 1, hash_size))
    diff = resized[:, 1:] > resized[:, :-1]
    return sum([2 ** i for (i, v) in enumerate(diff.flatten()) if v])


def hamming(a, b):
    return bin(a ^ b).count("1")


def variance_of_laplacian(image):
    return cv2.Laplacian(image, cv2.CV_64F).var()


def main():
    parser = argparse.ArgumentParser(description="Basic frame quality check")
    parser.add_argument("--frames", required=True, help="Directory containing extracted frames")
    parser.add_argument("--report", required=True, help="Output report path")
    args = parser.parse_args()

    frame_dir = Path(args.frames)
    files = sorted(frame_dir.glob("frame_*.jpg"))
    if not files:
        print("No frame files found", flush=True)
        return 1

    hashes = []
    report_lines = []
    duplicate_threshold = 10
    blur_threshold = 100.0

    for path in files:
        img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        lap = variance_of_laplacian(img)
        h = dhash(img)
        hashes.append((path.name, h, lap))
        report_lines.append(f"{path.name}, laplacian={lap:.2f}, hash={h}")

    duplicates = []
    for i in range(1, len(hashes)):
        prev = hashes[i - 1]
        cur = hashes[i]
        if hamming(prev[1], cur[1]) <= duplicate_threshold:
            duplicates.append((prev[0], cur[0], hamming(prev[1], cur[1])))

    blur_count = len([x for x in hashes if x[2] < blur_threshold])
    with open(args.report, "w") as out:
        out.write("Frame quality report\n")
        out.write("====================\n")
        out.write(f"Total frames: {len(hashes)}\n")
        out.write(f"Blur count (<{blur_threshold}): {blur_count}\n")
        out.write(f"Duplicate pair count (<={duplicate_threshold}): {len(duplicates)}\n")
        out.write("\nFrame details:\n")
        out.write("\n".join(report_lines))
        if duplicates:
            out.write("\n\nDuplicate frames:\n")
            for a, b, d in duplicates:
                out.write(f"{a} and {b} distance={d}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
