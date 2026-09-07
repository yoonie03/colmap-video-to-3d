"""Background orchestration for the Crack3D desktop application."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


class PipelineWorker(QObject):
    stage_changed = pyqtSignal(int, int, str)
    log_line = pyqtSignal(str)
    completed = pyqtSignal(dict)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()
    finished = pyqtSignal()

    def __init__(self, repo_root: Path, video: Path, output_root: Path, project: str, settings: dict, resume: bool = False) -> None:
        super().__init__()
        self.repo_root = repo_root.resolve()
        self.video = video.resolve()
        self.output_root = output_root.resolve()
        self.project = project
        self.settings = settings
        self.resume = resume
        self._cancel_requested = False
        self._process: subprocess.Popen[str] | None = None

    @pyqtSlot()
    def cancel(self) -> None:
        self._cancel_requested = True
        process = self._process
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def _run_command(self, command: list[str], label: str) -> None:
        if self._cancel_requested:
            raise InterruptedError
        self.log_line.emit(f"$ {' '.join(command)}")
        self._process = subprocess.Popen(
            command,
            cwd=self.repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        assert self._process.stdout is not None
        recent_lines: list[str] = []
        important_lines: list[str] = []
        for line in self._process.stdout:
            clean_line = line.rstrip()
            self.log_line.emit(clean_line)
            recent_lines.append(clean_line)
            recent_lines = recent_lines[-12:]
            lowered = clean_line.lower()
            if any(marker in lowered for marker in (
                "error", "failure", "failed", "no images with matches",
                "unsupported toolchain", "out of memory",
            )):
                important_lines.append(clean_line)
                important_lines = important_lines[-8:]
            if self._cancel_requested:
                self.cancel()
        return_code = self._process.wait()
        self._process = None
        if self._cancel_requested:
            raise InterruptedError
        if return_code:
            details = important_lines or recent_lines[-6:]
            detail_text = "\n".join(details)
            raise RuntimeError(
                f"{label} 단계가 실패했습니다 (종료 코드 {return_code})."
                + (f"\n\n마지막 오류:\n{detail_text}" if detail_text else "")
            )

    @pyqtSlot()
    def run(self) -> None:
        try:
            self._execute()
        except InterruptedError:
            self.cancelled.emit()
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.finished.emit()

    def _execute(self) -> None:
        if not self.video.is_file():
            raise FileNotFoundError(f"영상을 찾을 수 없습니다: {self.video}")
        ai_python = self.repo_root / ".venv-crack" / "bin" / "python"
        if not ai_python.is_file():
            raise FileNotFoundError(f"AI 실행 환경이 없습니다: {ai_python}")

        result_dir = self.output_root / "result" / self.project
        workspace_dir = self.output_root / "workspace" / self.project
        # Dense camera intrinsics describe these undistorted images, not the
        # original extracted frames (which can have different sizes/distortion).
        frames_dir = workspace_dir / "dense" / "images"
        crack_dir = result_dir / "crack_detection"
        model_txt = result_dir / "02_sparse" / "model_txt"
        total_stages = 4
        started = time.time()

        run_manifest = result_dir / "crack3d_run.json"
        if self.resume:
            required = [workspace_dir / "dense" / name for name in (
                "fused.ply", "fused.ply.vis", "stereo/fusion.cfg",
                "sparse/cameras.bin", "sparse/images.bin", "sparse/points3D.bin",
            )]
            if not all(path.is_file() and path.stat().st_size > 0 for path in required) or not frames_dir.is_dir():
                raise RuntimeError("이어하기에 필요한 3D 재구성 결과가 없습니다. '교체하고 처음부터'로 실행해 주세요.")
            if run_manifest.is_file():
                previous = json.loads(run_manifest.read_text(encoding="utf-8"))
                keys = ("fps", "max_size", "quality")
                if previous.get("video") != str(self.video) or any(
                    previous.get("settings", {}).get(key) != self.settings[key] for key in keys
                ):
                    raise RuntimeError("이전 영상 또는 3D 재구성 설정과 다릅니다. 이전 설정을 사용하거나 '교체하고 처음부터'로 실행해 주세요.")
            else:
                self.log_line.emit("이전 실행 정보가 없어 기존 3D 결과를 사용합니다. 같은 영상과 재구성 설정이어야 합니다.")

        self.stage_changed.emit(1, total_stages, "프레임 추출 및 3D 재구성")
        reconstruction = [
            "bash", str(self.repo_root / "scripts" / "run_video_to_3d.sh"),
            "--video", str(self.video),
            "--project-name", self.project,
            "--output-root", str(self.output_root),
            "--fps", str(self.settings["fps"]),
            "--max-size", str(self.settings["max_size"]),
            "--quality", self.settings["quality"],
            "--keep-frames", "--force", "--cpu-sift",
        ]
        if self.resume:
            self.log_line.emit("[이어하기] 완료된 3D 재구성 결과 사용")
        else:
            self._run_command(reconstruction, "3D 재구성")
        run_manifest.write_text(json.dumps({"video": str(self.video), "settings": self.settings}, ensure_ascii=False, indent=2), encoding="utf-8")

        self.stage_changed.emit(2, total_stages, "카메라 모델 내보내기")
        dense_sparse = workspace_dir / "dense" / "sparse"
        if not dense_sparse.is_dir():
            raise FileNotFoundError(f"COLMAP dense 카메라 모델이 없습니다: {dense_sparse}")
        model_txt.mkdir(parents=True, exist_ok=True)
        self._run_command([
            "colmap", "model_converter", "--input_path", str(dense_sparse),
            "--output_path", str(model_txt), "--output_type", "TXT",
        ], "카메라 모델 내보내기")

        self.stage_changed.emit(3, total_stages, "균열 AI 검출")
        if not frames_dir.is_dir() or not any(frames_dir.iterdir()):
            raise RuntimeError(f"균열 검출에 필요한 왜곡 보정 이미지가 없습니다: {frames_dir}")
        detection_command = [
            str(ai_python), str(self.repo_root / "crack_pipeline" / "run.py"),
            "--frames-dir", str(frames_dir), "--output-dir", str(crack_dir),
            "--weights", str(self.repo_root / "crack_pipeline" / "weights" / "dice.pt"),
            "--device", self.settings["device"], "--threshold", str(self.settings["threshold"]),
            "--tile-size", "512", "--overlap", "64", "--batch-size", "4",
            "--min-area", str(self.settings["min_area"]), "--fps", str(self.settings["fps"]),
            "--overwrite",
        ]
        if self.resume and detection_complete(frames_dir, crack_dir, self.settings):
            self.log_line.emit("[이어하기] 완료된 균열 AI 검출 결과 사용")
        else:
            self.log_line.emit("왜곡 보정 이미지로 균열을 검출합니다. 이전 원본 이미지의 마스크는 재사용하지 않습니다.")
            # An interrupted rerun must not leave an old completion marker behind.
            (crack_dir / "summary.json").unlink(missing_ok=True)
            self._run_command(detection_command, "균열 AI 검출")

        self.stage_changed.emit(4, total_stages, "균열 후보를 3D 포인트에 투영")
        point_cloud = workspace_dir / "dense" / "fused.ply"
        projection_output = crack_dir / "point_cloud_cracks.ply"
        self._run_command([
            sys.executable, str(self.repo_root / "crack_pipeline" / "project_to_pointcloud.py"),
            "--point-cloud", str(point_cloud),
            "--visibility", str(workspace_dir / "dense" / "fused.ply.vis"),
            "--fusion-config", str(workspace_dir / "dense" / "stereo" / "fusion.cfg"),
            "--cameras", str(model_txt / "cameras.txt"), "--images", str(model_txt / "images.txt"),
            "--masks-dir", str(crack_dir / "masks"), "--output", str(projection_output),
            "--summary", str(crack_dir / "point_cloud_cracks.json"),
            "--min-views", str(self.settings["min_views"]),
            "--mask-dilation", str(self.settings["mask_dilation"]),
        ], "3D 균열 투영")

        project_data = {
            "project": self.project,
            "video": str(self.video),
            "output_root": str(self.output_root),
            "result_dir": str(result_dir),
            "point_cloud": str(projection_output),
            "crack_summary": str(crack_dir / "summary.json"),
            "projection_summary": str(crack_dir / "point_cloud_cracks.json"),
            "overlay_video": str(crack_dir / "crack_overlay.mp4"),
            "completed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_seconds": time.time() - started,
            "settings": self.settings,
        }
        (result_dir / "crack3d_project.json").write_text(
            json.dumps(project_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.completed.emit(project_data)


def detection_complete(frames_dir: Path, crack_dir: Path, settings: dict) -> bool:
    try:
        summary = json.loads((crack_dir / "summary.json").read_text(encoding="utf-8"))
        if summary.get("input_dir") != str(frames_dir.resolve()):
            return False
        if any(summary["settings"].get(key) != settings[key] for key in ("threshold", "min_area", "fps")):
            return False
        frames = {path.name for path in frames_dir.iterdir() if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}}
        if not frames or frames != {record["frame"] for record in summary["frames"]}:
            return False
        return all((crack_dir / "masks" / f"{Path(name).stem}.png").is_file()
                   and (crack_dir / "masks" / f"{Path(name).stem}.png").stat().st_size > 0 for name in frames)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def load_existing_project(result_dir: Path) -> dict:
    result_dir = result_dir.resolve()
    manifest = result_dir / "crack3d_project.json"
    if manifest.is_file():
        return json.loads(manifest.read_text(encoding="utf-8"))
    crack_dir = result_dir / "crack_detection"
    point_cloud = crack_dir / "point_cloud_cracks.ply"
    if not point_cloud.is_file():
        raise FileNotFoundError(f"Crack3D 결과 PLY가 없습니다: {point_cloud}")
    return {
        "project": result_dir.name,
        "result_dir": str(result_dir),
        "point_cloud": str(point_cloud),
        "crack_summary": str(crack_dir / "summary.json"),
        "projection_summary": str(crack_dir / "point_cloud_cracks.json"),
        "overlay_video": str(crack_dir / "crack_overlay.mp4"),
    }
