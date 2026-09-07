#!/usr/bin/env python3
"""Crack3D desktop application."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import QThread, Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QFont, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFileDialog,
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from pipeline_worker import PipelineWorker, load_existing_project
from viewer import PointCloudViewer


REPO_ROOT = Path(__file__).resolve().parents[1]


class ScaledImageLabel(QLabel):
    """Image label that follows its layout instead of keeping a pixel size."""

    def __init__(self, placeholder: str = "", parent=None) -> None:
        super().__init__(placeholder, parent)
        self._source_pixmap = QPixmap()
        self.setAlignment(Qt.AlignCenter)

    def set_image(self, path: Path) -> None:
        self._source_pixmap = QPixmap(str(path))
        self.setText("")
        self._rescale()

    def clear_image(self, message: str = "") -> None:
        self._source_pixmap = QPixmap()
        self.setPixmap(QPixmap())
        self.setText(message)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self) -> None:
        if not self._source_pixmap.isNull() and self.width() > 10 and self.height() > 10:
            self.setPixmap(self._source_pixmap.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))


class ClickableImage(ScaledImageLabel):
    def __init__(self, path: Path, caption: str, on_click, parent=None) -> None:
        super().__init__(parent=parent)
        self.path = path
        self.on_click = on_click
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(caption)
        self.set_image(path)
        self.setMinimumSize(110, 82)
        self.setMaximumHeight(145)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setFrameShape(QFrame.StyledPanel)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.on_click(self.path)


class MainWindow(QMainWindow):
    def __init__(self, initial_project: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Crack3D · 영상 기반 균열 3D 시각화")
        self.setWindowIcon(QIcon(str(REPO_ROOT / "crack_gui" / "crack3d.svg")))
        self._thread: QThread | None = None
        self._worker: PipelineWorker | None = None
        self._current_project: dict | None = None
        self._build_ui()
        self._apply_style()
        self._configure_for_screen()
        if initial_project:
            try:
                self.display_project(load_existing_project(initial_project))
            except Exception as error:
                QMessageBox.warning(self, "프로젝트 열기 실패", str(error))

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 16, 20, 18)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Crack3D")
        title.setObjectName("title")
        subtitle = QLabel("영상 한 개로 균열 후보 검출부터 3D 포인트클라우드까지")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        self.open_project_button = QPushButton("기존 결과 열기")
        self.open_project_button.clicked.connect(self.choose_existing_project)
        header.addWidget(self.open_project_button)
        outer.addLayout(header)

        input_group = QGroupBox("새 영상 분석")
        input_layout = QGridLayout(input_group)
        self.input_layout = input_layout
        input_layout.setHorizontalSpacing(14)
        input_layout.setVerticalSpacing(12)
        input_layout.setColumnStretch(1, 5)
        input_layout.setColumnStretch(4, 3)
        self.video_edit = QLineEdit()
        self.video_edit.setPlaceholderText("분석할 영상 파일을 선택하세요")
        browse_video = QPushButton("영상 선택")
        browse_video.clicked.connect(self.choose_video)
        self.browse_video_button = browse_video
        self.project_edit = QLineEdit()
        self.project_edit.setPlaceholderText("프로젝트 이름")
        self.output_edit = QLineEdit(str(REPO_ROOT / "bench_3d"))
        browse_output = QPushButton("출력 위치")
        browse_output.clicked.connect(self.choose_output)
        self.browse_output_button = browse_output
        self.start_button = QPushButton("분석 시작")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start_pipeline)
        self.cancel_button = QPushButton("중지")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_pipeline)
        self.settings_button = QPushButton("고급 설정  ▾")
        self.settings_button.setCheckable(True)
        self.settings_button.toggled.connect(self.toggle_advanced)
        video_label = QLabel("영상 파일")
        video_label.setMinimumWidth(78)
        self.video_label = video_label
        project_label = QLabel("프로젝트")
        project_label.setMinimumWidth(78)
        self.project_label = project_label
        output_label = QLabel("결과 위치")
        output_label.setMinimumWidth(78)
        self.output_label = output_label
        input_layout.addWidget(video_label, 0, 0)
        input_layout.addWidget(self.video_edit, 0, 1, 1, 4)
        input_layout.addWidget(browse_video, 0, 5)
        input_layout.addWidget(project_label, 1, 0)
        input_layout.addWidget(self.project_edit, 1, 1)
        input_layout.addWidget(output_label, 1, 2)
        input_layout.addWidget(self.output_edit, 1, 3, 1, 2)
        input_layout.addWidget(browse_output, 1, 5)
        input_layout.addWidget(self.settings_button, 0, 6)
        input_layout.addWidget(self.start_button, 0, 7, 2, 1)
        input_layout.addWidget(self.cancel_button, 1, 6)

        self.advanced = QGroupBox("고급 설정")
        advanced_grid = QGridLayout(self.advanced)
        advanced_grid.setHorizontalSpacing(16)
        advanced_grid.setVerticalSpacing(10)
        self.fps_spin = QDoubleSpinBox(); self.fps_spin.setRange(0.2, 30); self.fps_spin.setValue(2); self.fps_spin.setSuffix(" fps")
        self.max_size_spin = QSpinBox(); self.max_size_spin.setRange(640, 4096); self.max_size_spin.setValue(1920)
        self.quality_combo = QComboBox(); self.quality_combo.addItems(["medium", "high", "low"])
        self.threshold_spin = QDoubleSpinBox(); self.threshold_spin.setRange(0.05, 0.95); self.threshold_spin.setSingleStep(0.05); self.threshold_spin.setValue(0.5)
        self.min_area_spin = QSpinBox(); self.min_area_spin.setRange(0, 10000); self.min_area_spin.setValue(20)
        self.min_views_spin = QSpinBox(); self.min_views_spin.setRange(1, 20); self.min_views_spin.setValue(1)
        self.dilation_spin = QSpinBox(); self.dilation_spin.setRange(0, 20); self.dilation_spin.setValue(2)
        self.device_combo = QComboBox(); self.device_combo.addItems(["auto", "cuda", "cpu"])
        advanced_fields = [
            ("프레임 추출", self.fps_spin), ("최대 이미지 크기", self.max_size_spin),
            ("COLMAP 품질", self.quality_combo), ("AI 임계값", self.threshold_spin),
            ("최소 2D 영역", self.min_area_spin), ("최소 관측 횟수", self.min_views_spin),
            ("마스크 확장", self.dilation_spin), ("AI 장치", self.device_combo),
        ]
        for index, (label, widget) in enumerate(advanced_fields):
            row = index // 4
            column = (index % 4) * 2
            advanced_grid.addWidget(QLabel(label), row, column)
            advanced_grid.addWidget(widget, row, column + 1)
            advanced_grid.setColumnStretch(column + 1, 1)
        self.advanced.hide()

        outer.addWidget(input_group)
        outer.addWidget(self.advanced)

        progress_row = QHBoxLayout()
        self.stage_label = QLabel("대기 중")
        self.progress = QProgressBar()
        self.progress.setRange(0, 4)
        self.progress.setValue(0)
        progress_row.addWidget(self.stage_label)
        progress_row.addWidget(self.progress, 1)
        outer.addLayout(progress_row)

        self.splitter = QSplitter(Qt.Horizontal)
        self.viewer = PointCloudViewer()
        self.splitter.addWidget(self.viewer)

        right_tabs = QTabWidget()
        gallery_tab = QWidget()
        gallery_layout = QVBoxLayout(gallery_tab)
        self.summary_label = QLabel("아직 분석 결과가 없습니다.")
        self.summary_label.setObjectName("summaryLabel")
        self.summary_label.setWordWrap(True)
        gallery_layout.addWidget(self.summary_label)
        self.hero_image = ScaledImageLabel("대표 검출 이미지를 선택하면 크게 표시됩니다.")
        self.hero_image.setMinimumHeight(150)
        self.hero_image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.hero_image.setFrameShape(QFrame.StyledPanel)
        gallery_layout.addWidget(self.hero_image)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        self.thumb_widget = QWidget(); self.thumb_layout = QGridLayout(self.thumb_widget)
        scroll.setWidget(self.thumb_widget)
        gallery_layout.addWidget(scroll, 1)
        actions = QHBoxLayout()
        self.open_folder_button = QPushButton("결과 폴더")
        self.open_folder_button.setEnabled(False)
        self.open_folder_button.clicked.connect(self.open_result_folder)
        self.open_video_button = QPushButton("오버레이 영상")
        self.open_video_button.setEnabled(False)
        self.open_video_button.clicked.connect(self.open_overlay_video)
        actions.addWidget(self.open_folder_button); actions.addWidget(self.open_video_button)
        gallery_layout.addLayout(actions)
        right_tabs.addTab(gallery_tab, "대표 검출")

        log_tab = QWidget(); log_layout = QVBoxLayout(log_tab)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        log_layout.addWidget(self.log)
        right_tabs.addTab(log_tab, "실행 로그")
        self.right_tabs = right_tabs
        self.splitter.addWidget(right_tabs)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        outer.addWidget(self.splitter, 1)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #11151d; color: #e8edf5; font-size: 11pt; }
            QGroupBox { border: 1px solid #30394a; border-radius: 9px; margin-top: 12px; padding: 14px; font-weight: 650; }
            QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 7px; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit { background: #1b2230; border: 1px solid #3d4960; border-radius: 6px; padding: 9px; min-height: 24px; selection-background-color: #d84b36; }
            QPushButton { background: #273146; border: 1px solid #465571; border-radius: 7px; padding: 10px 16px; min-height: 22px; font-weight: 600; }
            QPushButton:hover { background: #34415a; }
            QPushButton:disabled { color: #717988; background: #202633; }
            #primaryButton { background: #e64a32; border-color: #ff7159; font-weight: 750; min-width: 110px; font-size: 12pt; }
            #primaryButton:hover { background: #f15c44; }
            #title { font-size: 23pt; font-weight: 800; color: #ff7058; }
            #subtitle { color: #aeb9cc; font-size: 10pt; }
            #viewerStatus { color: #bdc7d8; padding: 7px; font-size: 10pt; }
            #summaryLabel { font-size: 11pt; padding: 7px; }
            QProgressBar { border: 1px solid #344056; border-radius: 6px; text-align: center; background: #1b2230; min-height: 24px; font-size: 10pt; }
            QProgressBar::chunk { background: #e64a32; border-radius: 4px; }
            QTabWidget::pane { border: 1px solid #30394a; }
            QTabBar::tab { background: #1b2230; padding: 9px 16px; font-size: 11pt; }
            QTabBar::tab:selected { background: #30394a; }
        """)

    def _configure_for_screen(self) -> None:
        """Size the UI in Qt logical pixels so desktop scaling stays respected."""
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1200, 800)
            return
        available = screen.availableGeometry()
        width = min(available.width(), max(760, int(available.width() * 0.94)))
        height = min(available.height(), max(560, int(available.height() * 0.92)))
        self.resize(width, height)
        self.setMinimumSize(min(760, available.width()), min(560, available.height()))
        self.move(
            available.x() + max(0, (available.width() - width) // 2),
            available.y() + max(0, (available.height() - height) // 2),
        )
        narrow = available.width() < 1050
        short = available.height() < 760
        self._layout_input(narrow)
        result_width = max(280, int(width * (0.31 if narrow else 0.27)))
        self.right_tabs.setMinimumWidth(min(result_width, int(width * 0.42)))
        self.splitter.setSizes([max(1, width - result_width), result_width])
        self.hero_image.setMinimumHeight(110 if short else 170)

    def _layout_input(self, compact: bool) -> None:
        widgets = [
            self.video_label, self.video_edit, self.browse_video_button,
            self.project_label, self.project_edit, self.output_label, self.output_edit,
            self.browse_output_button, self.settings_button, self.start_button, self.cancel_button,
        ]
        for widget in widgets:
            self.input_layout.removeWidget(widget)
        for column in range(8):
            self.input_layout.setColumnStretch(column, 0)
        if compact:
            self.input_layout.addWidget(self.video_label, 0, 0)
            self.input_layout.addWidget(self.video_edit, 0, 1, 1, 3)
            self.input_layout.addWidget(self.browse_video_button, 0, 4)
            self.input_layout.addWidget(self.project_label, 1, 0)
            self.input_layout.addWidget(self.project_edit, 1, 1, 1, 3)
            self.input_layout.addWidget(self.output_label, 2, 0)
            self.input_layout.addWidget(self.output_edit, 2, 1, 1, 3)
            self.input_layout.addWidget(self.browse_output_button, 2, 4)
            self.input_layout.addWidget(self.settings_button, 3, 0, 1, 2)
            self.input_layout.addWidget(self.cancel_button, 3, 2)
            self.input_layout.addWidget(self.start_button, 3, 3, 1, 2)
            self.input_layout.setColumnStretch(1, 2)
            self.input_layout.setColumnStretch(3, 2)
        else:
            self.input_layout.addWidget(self.video_label, 0, 0)
            self.input_layout.addWidget(self.video_edit, 0, 1, 1, 4)
            self.input_layout.addWidget(self.browse_video_button, 0, 5)
            self.input_layout.addWidget(self.project_label, 1, 0)
            self.input_layout.addWidget(self.project_edit, 1, 1)
            self.input_layout.addWidget(self.output_label, 1, 2)
            self.input_layout.addWidget(self.output_edit, 1, 3, 1, 2)
            self.input_layout.addWidget(self.browse_output_button, 1, 5)
            self.input_layout.addWidget(self.settings_button, 0, 6)
            self.input_layout.addWidget(self.cancel_button, 1, 6)
            self.input_layout.addWidget(self.start_button, 0, 7, 2, 1)
            self.input_layout.setColumnStretch(1, 5)
            self.input_layout.setColumnStretch(4, 3)

    def toggle_advanced(self, visible: bool) -> None:
        self.advanced.setVisible(visible)
        self.settings_button.setText("고급 설정  ▴" if visible else "고급 설정  ▾")

    def choose_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "분석할 영상 선택", str(REPO_ROOT / "bench_3d" / "video"), "Video (*.mov *.mp4 *.avi *.mkv *.MOV)")
        if path:
            self.video_edit.setText(path)
            safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(path).stem).strip("_")
            self.project_edit.setText(safe_name or "crack3d_project")

    def choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "결과 루트 선택", self.output_edit.text())
        if path:
            self.output_edit.setText(path)

    def choose_existing_project(self) -> None:
        base = Path(self.output_edit.text() or REPO_ROOT / "bench_3d") / "result"
        path = QFileDialog.getExistingDirectory(self, "기존 결과 폴더 선택", str(base))
        if path:
            try:
                self.display_project(load_existing_project(Path(path)))
            except Exception as error:
                QMessageBox.warning(self, "결과 열기 실패", str(error))

    def _settings(self) -> dict:
        return {
            "fps": self.fps_spin.value(), "max_size": self.max_size_spin.value(),
            "quality": self.quality_combo.currentText(), "threshold": self.threshold_spin.value(),
            "min_area": self.min_area_spin.value(), "min_views": self.min_views_spin.value(),
            "mask_dilation": self.dilation_spin.value(), "device": self.device_combo.currentText(),
        }

    def start_pipeline(self) -> None:
        video = Path(self.video_edit.text()).expanduser()
        output_root = Path(self.output_edit.text()).expanduser()
        project = self.project_edit.text().strip()
        if not video.is_file():
            QMessageBox.warning(self, "입력 확인", "유효한 영상 파일을 선택해 주세요.")
            return
        if not re.fullmatch(r"[A-Za-z0-9_-]+", project):
            QMessageBox.warning(self, "프로젝트 이름", "프로젝트 이름에는 영문, 숫자, _, -만 사용할 수 있습니다.")
            return
        output_root = self._normalize_output_root(output_root, project)
        self.output_edit.setText(str(output_root))
        existing = output_root / "result" / project
        resume = False
        if existing.exists() or (output_root / "workspace" / project).exists():
            dialog = QMessageBox(self)
            dialog.setWindowTitle("기존 프로젝트")
            dialog.setText(f"{existing}\n기존 결과를 이어서 처리할까요?")
            dialog.setInformativeText("이어하기는 완료된 3D 재구성과 균열 검출 결과를 재사용합니다.\n이전과 같은 영상과 설정을 선택해 주세요.\n3D 재구성 도중 중단된 작업은 처음부터 다시 실행해야 합니다.")
            resume_button = dialog.addButton("이어하기", QMessageBox.AcceptRole)
            replace_button = dialog.addButton("교체하고 처음부터", QMessageBox.DestructiveRole)
            dialog.addButton("취소", QMessageBox.RejectRole)
            dialog.setDefaultButton(resume_button)
            dialog.exec_()
            if dialog.clickedButton() not in (resume_button, replace_button):
                return
            resume = dialog.clickedButton() == resume_button
        output_root.mkdir(parents=True, exist_ok=True)
        self.log.clear()
        self._set_running(True)
        self._thread = QThread(self)
        self._worker = PipelineWorker(REPO_ROOT, video, output_root, project, self._settings(), resume=resume)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.stage_changed.connect(self.on_stage)
        self._worker.log_line.connect(self.log.append)
        self._worker.completed.connect(self.on_completed)
        self._worker.failed.connect(self.on_failed)
        self._worker.cancelled.connect(self.on_cancelled)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(lambda: self._set_running(False))
        self._thread.start()

    @staticmethod
    def _normalize_output_root(path: Path, project: str) -> Path:
        """Recover when a user selects result/PROJECT instead of the workspace root."""
        path = path.resolve()
        if path.name == project and path.parent.name == "result":
            return path.parent.parent
        if path.name == "result":
            return path.parent
        return path

    def cancel_pipeline(self) -> None:
        if self._worker:
            self.stage_label.setText("중지 요청 중…")
            self._worker.cancel()

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.open_project_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        if not running:
            self._worker = None
            self._thread = None

    def on_stage(self, current: int, total: int, name: str) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(current - 1)
        self.stage_label.setText(f"{current}/{total} · {name}")

    def on_completed(self, project: dict) -> None:
        self.progress.setValue(self.progress.maximum())
        self.stage_label.setText("분석 완료")
        self.display_project(project)
        QMessageBox.information(self, "완료", "균열 후보 검출과 3D 투영이 완료됐습니다.")

    def on_failed(self, message: str) -> None:
        self.stage_label.setText("분석 실패")
        QMessageBox.critical(self, "분석 실패", message)

    def on_cancelled(self) -> None:
        self.stage_label.setText("사용자가 분석을 중지했습니다.")

    def display_project(self, project: dict) -> None:
        self._current_project = project
        point_cloud = Path(project["point_cloud"])
        self.viewer.load_ply(point_cloud)
        crack_summary = self._read_json(Path(project["crack_summary"]))
        projection = self._read_json(Path(project["projection_summary"]))
        aggregate = crack_summary.get("aggregate", {})
        self.summary_label.setText(
            f"프로젝트: {project.get('project', point_cloud.parent.parent.name)}\n"
            f"분석 프레임: {aggregate.get('frame_count', 0):,}장 · "
            f"2D 후보 프레임: {aggregate.get('frames_with_candidates', 0):,}장\n"
            f"3D 포인트: {projection.get('point_count', 0):,}개 · "
            f"빨간 후보점: {projection.get('crack_point_count', 0):,}개"
        )
        self._populate_gallery(Path(project["crack_summary"]), crack_summary)
        self.open_folder_button.setEnabled(True)
        self.open_video_button.setEnabled(Path(project["overlay_video"]).is_file())

    @staticmethod
    def _read_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    def _populate_gallery(self, summary_path: Path, summary: dict) -> None:
        while self.thumb_layout.count():
            item = self.thumb_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        frames = [frame for frame in summary.get("frames", []) if frame.get("crack_pixels", 0) > 0]
        frames.sort(key=lambda frame: (frame.get("crack_pixels", 0), frame.get("max_probability", 0)), reverse=True)
        selected = []
        for frame in frames:
            number_match = re.search(r"(\d+)", frame["frame"])
            number = int(number_match.group(1)) if number_match else -1000
            if all(abs(number - old_number) >= 3 for old_number, _ in selected):
                selected.append((number, frame))
            if len(selected) == 6:
                break
        overlay_dir = summary_path.parent / "overlays"
        first_path = None
        for index, (_, frame) in enumerate(selected):
            path = overlay_dir / f"{Path(frame['frame']).stem}.png"
            if not path.is_file():
                continue
            if first_path is None:
                first_path = path
            caption = f"{frame['frame']} · {frame['crack_pixels']:,}px"
            self.thumb_layout.addWidget(ClickableImage(path, caption, self.show_hero), index // 2, index % 2)
        if first_path:
            self.show_hero(first_path)
        else:
            self.hero_image.clear_image("검출된 균열 후보가 없습니다.")

    def show_hero(self, path: Path) -> None:
        self.hero_image.set_image(path)
        self.hero_image.setToolTip(str(path))

    def open_result_folder(self) -> None:
        if self._current_project:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._current_project["result_dir"]))

    def open_overlay_video(self) -> None:
        if self._current_project:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._current_project["overlay_video"]))

    def closeEvent(self, event) -> None:
        if self._worker:
            answer = QMessageBox.question(self, "분석 중", "분석을 중지하고 종료할까요?", QMessageBox.Yes | QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore(); return
            self._worker.cancel()
        event.accept()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--open-project", type=Path, help="Open an existing result directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    application = QApplication(sys.argv)
    application.setApplicationName("Crack3D")
    application.setFont(QFont("Sans Serif", 11))
    window = MainWindow(args.open_project)
    window.show()
    return application.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
