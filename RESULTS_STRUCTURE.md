# 3D 재구성 결과 폴더 구조

로컬 실행 결과는 프로젝트별로 다음 구조에 정리한다.

```text
bench_3d/result/{project}/
├── 02_sparse/
│   ├── model_bin/              # COLMAP 카메라·이미지 자세·Sparse 모델
│   ├── model_txt/              # 사람이 읽을 수 있는 카메라·이미지 자세·3D 점
│   └── sparse_point_cloud.ply  # 뷰어에서 열 수 있는 Sparse point cloud
├── 03_dense/
│   └── dense_point_cloud.ply   # 조밀한 컬러 point cloud
└── 04_mesh/
    └── mesh.ply                # 표면 triangle mesh
```

## 파일 용도

- `02_sparse/model_bin`: COLMAP에서 reconstruction으로 다시 열 때 사용한다.
- `02_sparse/model_txt/images.txt`: 이미지별 카메라 자세를 확인한다.
- `02_sparse/model_txt/cameras.txt`: 카메라 모델과 내부 파라미터를 확인한다.
- `02_sparse/model_txt/points3D.txt`: Sparse 3D 점과 관측 track을 확인한다.
- `02_sparse/sparse_point_cloud.ply`: MeshLab 등의 PLY 뷰어에서 Sparse 점을 확인한다.
- `03_dense/dense_point_cloud.ply`: 컬러 포인트클라우드 결과다.
- `04_mesh/mesh.ply`: 최종 triangle mesh 결과다.

원본 영상과 생성된 PLY·COLMAP 모델은 개인정보와 파일 크기를 고려해 Git 저장소에 포함하지 않는다.

`fan_1`은 5fps 재시도 결과를 `02_sparse`~`04_mesh`에 저장하고, 2fps 실패 결과는 `baseline_2fps`에 보존한다.
