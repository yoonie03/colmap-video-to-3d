"""Embedded VTK point-cloud viewer for Crack3D."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import vtk
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget
from vtk.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy


def read_crack_labels(path: Path, point_count: int) -> np.ndarray | None:
    labels_path = path.with_suffix(".crack_labels.npy")
    if not labels_path.is_file():
        return None
    labels = np.load(labels_path, allow_pickle=False)
    if labels.dtype != np.bool_ or labels.shape != (point_count,):
        raise RuntimeError(f"균열 표시 데이터가 PLY와 맞지 않습니다: {labels_path}")
    return labels


class PointCloudViewer(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._renderer = vtk.vtkRenderer()
        self._renderer.SetBackground(0.055, 0.065, 0.08)
        self._vtk_widget = QVTKRenderWindowInteractor(self)
        self._vtk_widget.GetRenderWindow().AddRenderer(self._renderer)
        self._interactor = self._vtk_widget.GetRenderWindow().GetInteractor()
        self._interactor.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())
        self._main_actor = None
        self._crack_actor = None

        self.status = QLabel("분석이 끝나면 3D 포인트클라우드가 여기에 표시됩니다.")
        self.status.setObjectName("viewerStatus")
        self.status.setAlignment(Qt.AlignCenter)
        self.reset_button = QPushButton("전체 보기")
        self.reset_button.clicked.connect(self.reset_camera)
        self.point_size = QSlider(Qt.Horizontal)
        self.point_size.setRange(1, 8)
        self.point_size.setValue(2)
        self.point_size.setFixedWidth(120)
        self.point_size.valueChanged.connect(self._set_point_size)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.reset_button)
        toolbar.addStretch()
        toolbar.addWidget(QLabel("점 크기"))
        toolbar.addWidget(self.point_size)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.status)
        layout.addWidget(self._vtk_widget, 1)
        layout.addLayout(toolbar)
        self._vtk_widget.hide()

    def load_ply(self, path: Path) -> None:
        reader = vtk.vtkPLYReader()
        reader.SetFileName(str(path))
        reader.Update()
        polydata = reader.GetOutput()
        if polydata.GetNumberOfPoints() == 0:
            raise RuntimeError(f"PLY에 포인트가 없습니다: {path}")

        self._renderer.RemoveAllViewProps()
        point_vertices = vtk.vtkVertexGlyphFilter()
        point_vertices.SetInputData(polydata)
        point_vertices.Update()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(point_vertices.GetOutputPort())
        mapper.SetColorModeToDirectScalars()
        mapper.ScalarVisibilityOn()
        self._main_actor = vtk.vtkActor()
        self._main_actor.SetMapper(mapper)
        self._main_actor.GetProperty().SetRepresentationToPoints()
        self._main_actor.GetProperty().SetPointSize(self.point_size.value())
        self._renderer.AddActor(self._main_actor)

        self._crack_actor = None
        labels = read_crack_labels(path, polydata.GetNumberOfPoints())
        crack_count = 0
        if labels is not None:
            crack_indices = np.flatnonzero(labels)
            crack_count = len(crack_indices)
            if crack_count:
                all_points = vtk_to_numpy(polydata.GetPoints().GetData())
                crack_points_array = np.ascontiguousarray(all_points[crack_indices])
                points = vtk.vtkPoints()
                points.SetData(numpy_to_vtk(crack_points_array, deep=True))
                vertices = vtk.vtkCellArray()
                for index in range(crack_count):
                    vertices.InsertNextCell(1)
                    vertices.InsertCellPoint(index)
                crack_polydata = vtk.vtkPolyData()
                crack_polydata.SetPoints(points)
                crack_polydata.SetVerts(vertices)
                crack_mapper = vtk.vtkPolyDataMapper()
                crack_mapper.SetInputData(crack_polydata)
                self._crack_actor = vtk.vtkActor()
                self._crack_actor.SetMapper(crack_mapper)
                self._crack_actor.GetProperty().SetColor(1.0, 0.05, 0.02)
                self._crack_actor.GetProperty().SetPointSize(max(6, self.point_size.value() + 4))
                self._renderer.AddActor(self._crack_actor)

        candidate_status = f"균열 후보 {crack_count:,}점" if labels is not None else "균열 표시 데이터 없음 · 이어하기로 다시 생성"
        self.status.setText(f"{path.name} · {polydata.GetNumberOfPoints():,}점 · {candidate_status}")
        self.status.show()
        self._vtk_widget.show()
        self.reset_camera()
        self._interactor.Initialize()

    def reset_camera(self) -> None:
        self._renderer.ResetCamera()
        self._renderer.GetActiveCamera().Zoom(1.1)
        self._vtk_widget.GetRenderWindow().Render()

    def _set_point_size(self, value: int) -> None:
        if self._main_actor is not None:
            self._main_actor.GetProperty().SetPointSize(value)
        if self._crack_actor is not None:
            self._crack_actor.GetProperty().SetPointSize(max(6, value + 4))
        self._vtk_widget.GetRenderWindow().Render()
