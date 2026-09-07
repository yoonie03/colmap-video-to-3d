import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from crack_pipeline.project_to_pointcloud import read_images, VERTEX_DTYPE
from crack_gui.pipeline_worker import detection_complete
from crack_gui.viewer import read_crack_labels


class PipelineTests(unittest.TestCase):
    def test_empty_point_records_and_spaces(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'images.txt'
            path.write_text('# comment\n1 1 0 0 0 0 0 0 1 first image.jpg\n\n2 1 0 0 0 0 0 0 1 second.jpg\n0 0 -1\n')
            self.assertEqual(set(read_images(path)), {'first image.jpg', 'second.jpg'})

    def test_resume_checks_mask_content(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); frames = root / 'images'; masks = root / 'masks'
            frames.mkdir(); masks.mkdir()
            settings = dict(threshold=.5, min_area=20, fps=2)
            (root / 'summary.json').write_text(json.dumps(dict(input_dir=str(frames), settings=settings, frames=[dict(frame='a.png')])))
            cv2.imwrite(str(frames / 'a.png'), np.zeros((4, 6), np.uint8))
            mask = masks / 'a.png'
            mask.write_bytes(b'corrupt')
            self.assertFalse(detection_complete(frames, root, settings))
            cv2.imwrite(str(mask), np.zeros((3, 6), np.uint8))
            self.assertFalse(detection_complete(frames, root, settings))
            cv2.imwrite(str(mask), np.zeros((4, 6), np.uint8))
            self.assertTrue(detection_complete(frames, root, settings))
            mask.unlink()
            self.assertFalse(detection_complete(frames, root, settings))

    def test_projection_and_missing_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); masks = root / 'masks'; masks.mkdir()
            cloud = root / 'fused.ply'
            vertices = np.zeros(2, dtype=VERTEX_DTYPE)
            vertices['x'] = [0, 1]; vertices['z'] = 1
            vertices['red'] = [100, 255]  # Second point is naturally red, not a crack.
            header = 'ply\nformat binary_little_endian 1.0\nelement vertex 2\n'
            for name in VERTEX_DTYPE.names:
                header += f"property {'float' if name not in ('red', 'green', 'blue') else 'uchar'} {name}\n"
            cloud.write_bytes((header + 'end_header\n').encode() + vertices.tobytes())
            (root / 'vis').write_bytes(struct.pack('<QIIII', 2, 1, 0, 1, 0))
            (root / 'fusion.cfg').write_text('a.png\n')
            (root / 'cameras.txt').write_text('1 PINHOLE 4 4 1 1 0 0\n')
            poses = root / 'images.txt'; poses.write_text('1 1 0 0 0 0 0 0 1 a.png\n\n')
            mask = np.zeros((4, 4), np.uint8); mask[0, 0] = 255
            cv2.imwrite(str(masks / 'a.png'), mask)
            output = root / 'out.ply'
            command = [sys.executable, str(ROOT / 'crack_pipeline/project_to_pointcloud.py'), '--point-cloud', str(cloud), '--visibility', str(root/'vis'), '--fusion-config', str(root/'fusion.cfg'), '--cameras', str(root/'cameras.txt'), '--images', str(poses), '--masks-dir', str(masks), '--output', str(output), '--mask-dilation', '0']
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            np.testing.assert_array_equal(read_crack_labels(output, 2), [True, False])
            self.assertEqual(json.loads(output.with_suffix('.json').read_text())['crack_point_count'], 1)
            (masks / 'a.png').unlink()
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Missing mask', result.stderr)
            poses.write_text('1 1 0 0 0 0 0 0 1 other.png\n\n')
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Missing camera pose', result.stderr)

    def test_legacy_and_invalid_labels(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'cloud.ply'
            self.assertIsNone(read_crack_labels(path, 2))
            np.save(path.with_suffix('.crack_labels.npy'), np.zeros(3, dtype=bool))
            with self.assertRaises(RuntimeError):
                read_crack_labels(path, 2)


if __name__ == '__main__':
    unittest.main()
