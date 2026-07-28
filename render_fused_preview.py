#!/usr/bin/env python3
import pathlib

import numpy as np
from PIL import Image


SOURCE = pathlib.Path(__file__).parent / "bench_3d/workspace/bench_1/dense/fused.ply"
OUTPUT = pathlib.Path(__file__).parent / "bench_3d/result/bench_1/fused_preview.png"

with SOURCE.open("rb") as stream:
    header = b""
    while not header.endswith(b"end_header\n"):
        header += stream.readline()
    vertex_line = next(
        line for line in header.decode("ascii").splitlines()
        if line.startswith("element vertex ")
    )
    count = int(vertex_line.split()[-1])
    dtype = np.dtype([
        ("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
        ("nx", "<f4"), ("ny", "<f4"), ("nz", "<f4"),
        ("red", "u1"), ("green", "u1"), ("blue", "u1"),
    ])
    cloud = np.fromfile(stream, dtype=dtype, count=count)

step = max(1, len(cloud) // 500_000)
cloud = cloud[::step]
points = np.column_stack((cloud["x"], cloud["y"], cloud["z"])).astype(np.float64)
colors = np.column_stack((cloud["red"], cloud["green"], cloud["blue"]))

center = np.median(points, axis=0)
points -= center
_, _, axes = np.linalg.svd(points[::20], full_matrices=False)
view = points @ axes.T

width, height = 1600, 1000
x, y, depth = view[:, 0], view[:, 1], view[:, 2]
x0, x1 = np.percentile(x, [0.5, 99.5])
y0, y1 = np.percentile(y, [0.5, 99.5])
scale = min((width - 80) / (x1 - x0), (height - 80) / (y1 - y0))
px = ((x - (x0 + x1) / 2) * scale + width / 2).astype(np.int32)
py = (height / 2 - (y - (y0 + y1) / 2) * scale).astype(np.int32)
valid = (px >= 2) & (px < width - 2) & (py >= 2) & (py < height - 2)
px, py, depth, colors = px[valid], py[valid], depth[valid], colors[valid]

order = np.argsort(depth)
canvas = np.full((height, width, 3), 24, dtype=np.uint8)
for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
    canvas[py[order] + dy, px[order] + dx] = colors[order]

Image.fromarray(canvas).save(OUTPUT)
print(OUTPUT)
