# COLMAP 3D 재구성 결과 보고서

작성일: 2026-07-29  
환경: Ubuntu 24.04, NVIDIA GeForce RTX 5070 Ti, COLMAP 4.2.0.dev0, CUDA 13.3

## 요약

| 프로젝트 | 영상 길이 | 추출 프레임 | Sparse 등록 | Sparse 점 | Dense 포인트 | Mesh 버텍스 | Mesh 면 | 상태 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `bench_1` | 43.303초 | 87 | 87/87 (100%) | 23,627 | 1,092,915 | 3,301,858 | 6,484,165 | 완료 |
| `bridge_1` | 38.370초 | 77 | 74/77 (96.1%) | 8,434 | 377,653 | 962,386 | 1,883,722 | 완료 |
| `bench_2` | 41.370초 | 83 | 82/83 (98.8%) | 20,136 | 693,035 | 1,537,722 | 2,962,465 | 완료 |
| `fan_1` | 20.435초 | 102 | 35/102 (34.3%) | 1,484 | 227,345 | 183,326 | 337,951 | 부분 재구성 |

기본 조건은 2fps, 최대 긴 변 1280px이다. `fan_1`은 2fps에서 mesh가 생성되지 않아 5fps 재시도 결과를 채택했다.

## 처리 시간

### bridge_1

`bridge_1`은 오류 수정 후 전체 파이프라인을 한 번에 실행했으므로 실제 end-to-end 시간을 확인할 수 있다.

- 프레임 생성 시작: 2026-07-29 03:08:42
- 최종 `mesh.ply` 생성: 2026-07-29 03:27:47
- 총 경과 시간: 약 **19분 5초**

주요 단계:

| 단계 | 완료 시각 | 구간 시간 |
|---|---|---:|
| 프레임 추출 및 품질 검사 | 03:08:45 | 약 3초 |
| Feature extraction | 03:08:45 | 약 1초 |
| Exhaustive matching | 03:09:22 | 약 36초 |
| Sparse reconstruction | 03:09:28 | 약 6초 |
| Dense PatchMatch 및 fusion | 03:27:32 | 약 18분 3초 |
| Poisson mesh | 03:27:47 | 약 15초 |

Dense 단계가 전체 시간의 대부분을 차지한다. CUDA PTX 호환 레이어를 이용하는 현재 구성에서는 PatchMatch 속도가 네이티브 CUDA 코드보다 느리지만 결과 정확성을 보장한다.

### bench_1

`bench_1`은 최초 PTX 오류 분석, 여러 재빌드 및 잘못 생성된 중간 결과 제거가 포함되어 일반적인 처리 시간과 직접 비교하면 안 된다.

- 최초 프레임 생성 시작: 2026-07-29 01:26:05
- 최종 `mesh.ply` 생성: 2026-07-29 02:46:05
- 오류 분석을 포함한 총 경과 시간: 약 **1시간 20분**
- 최종 정상 PatchMatch 재실행부터 mesh 생성까지: 약 **25분 47초**
  - 정상 PatchMatch: 24분 42초
  - Stereo fusion: 약 13초
  - Poisson mesh: 약 52초

향후에는 수정된 실행 래퍼를 사용하므로 최초 오류 분석 및 재빌드 시간은 반복되지 않는다.

### bench_2

- 프레임 생성 시작: 2026-07-29 19:39:33
- 최종 `mesh.ply` 생성: 2026-07-29 20:05:05
- Sparse 다중 모델 선별 수정과 잘못 선택된 소형 모델 확인을 포함한 총 경과 시간: 약 **25분 32초**
- 올바른 82장 모델의 PatchMatch: 약 **22분 59초**
- Stereo fusion: 약 **6초**
- Poisson mesh: 약 **35초**

Mapper가 3장짜리 `sparse/0`과 82장짜리 `sparse/1`을 함께 생성했다. 기존 스크립트는 고정적으로 `sparse/0`을 사용해 dense fusion이 0점으로 끝났으므로, 등록 이미지 수가 가장 많은 sparse 모델을 자동 선택하도록 수정한 뒤 `sparse/1`로 dense reconstruction을 완료했다.

### fan_1

- 2fps 1차 실행: 약 **1분 28초**
  - 등록 이미지: 7/41
  - Dense points: 10,151
  - Mesh: 0 vertices / 0 faces
- 5fps 재시도 시작: 2026-07-29 20:19:25
- 5fps 최종 `mesh.ply` 생성: 2026-07-29 20:29:55
- 5fps 총 경과 시간: 약 **10분 30초**

2fps에서는 프레임 사이 시점 변화가 커 촬영 경로가 거의 연결되지 않았다. 5fps에서는 최대 모델이 35장으로 개선되어 Dense와 mesh가 생성됐지만 전체 102장 중 34.3%만 한 모델에 등록됐으므로 완전한 재구성이 아닌 부분 결과다.

## bench_1 상세 결과

### 입력 및 프레임

- 원본: `bench_3d/video/bench_1.MOV`
- 영상 크기: 48,212,930 bytes
- 영상 길이: 43.303초
- 추출 프레임: 87장
- 흐림 판정 프레임: 39장 (`Laplacian variance < 100`)
- 중복 프레임 쌍: 0

### Sparse reconstruction

- 카메라: 1
- 등록 이미지: 87/87
- Sparse 3D points: 23,627
- Observations: 120,691
- 평균 track length: 5.108
- 이미지당 평균 observation: 1,387.253
- 평균 reprojection error: 0.721px

평균 reprojection error가 1px보다 작고 모든 프레임이 등록되었으므로 sparse 정합 상태는 양호하다.

### Dense 및 mesh

- Fused points: 1,092,915
- Mesh vertices: 3,301,858
- Mesh faces: 6,484,165
- Fused PLY 크기: 약 29MB
- Mesh PLY 크기: 약 159MB

결과 파일:

- `bench_3d/workspace/bench_1/dense/fused.ply`
- `bench_3d/result/bench_1/mesh.ply`
- `bench_3d/result/bench_1/fused_preview.png`
- 분류본: `bench_3d/result/bench_1/02_sparse`, `03_dense`, `04_mesh`

## bridge_1 상세 결과

### 입력 및 프레임

- 원본: `bench_3d/video/bridge_1.MOV`
- 영상 크기: 60,850,481 bytes
- 영상 길이: 38.370초
- 추출 프레임: 77장
- 흐림 판정 프레임: 8장 (`Laplacian variance < 100`)
- 중복 프레임 쌍: 0

### Sparse reconstruction

- 카메라: 1
- 등록 이미지: 74/77
- 등록률: 96.1%
- Sparse 3D points: 8,434
- Observations: 30,119
- 평균 track length: 3.571
- 이미지당 평균 observation: 407.014
- 평균 reprojection error: 0.795px

3장은 주변 프레임과 충분한 특징점 대응을 확보하지 못해 등록되지 않았다. 등록된 74장만으로 dense reconstruction이 정상 완료되었다.

### Dense 및 mesh

- Fused points: 377,653
- Mesh vertices: 962,386
- Mesh faces: 1,883,722
- Point cloud PLY 크기: 약 9.8MB
- Mesh PLY 크기: 약 47MB

결과 파일:

- `bench_3d/workspace/bridge_1/dense/fused.ply`
- `bench_3d/result/bridge_1/point_cloud.ply`
- `bench_3d/result/bridge_1/mesh.ply`
- 분류본: `bench_3d/result/bridge_1/02_sparse`, `03_dense`, `04_mesh`

## bench_2 상세 결과

### 입력 및 프레임

- 원본: `bench_3d/video/bench_2.MOV`
- 영상 크기: 45,663,724 bytes
- 영상 길이: 41.370초
- 추출 프레임: 83장
- 흐림 판정 프레임: 36장 (`Laplacian variance < 100`)
- 중복 프레임 쌍: 0

### Sparse reconstruction

- 카메라: 1
- 등록 이미지: 82/83
- 등록률: 98.8%
- Sparse 3D points: 20,136
- Observations: 95,838
- 평균 track length: 4.760
- 이미지당 평균 observation: 1,168.756
- 평균 reprojection error: 0.673px

1장을 제외한 전체 촬영 경로가 하나의 모델로 연결되었고 평균 reprojection error도 1px보다 작아 sparse 정합 상태는 양호하다. 별도로 생성된 3장짜리 작은 모델은 최종 결과에 사용하지 않았다.

### Dense 및 mesh

- Fused points: 693,035
- Mesh vertices: 1,537,722
- Mesh faces: 2,962,465
- Point cloud PLY 크기: 약 18.7MB
- Mesh PLY 크기: 약 76.6MB

결과 파일:

- `bench_3d/workspace/bench_2/dense/fused.ply`
- `bench_3d/result/bench_2/point_cloud.ply`
- `bench_3d/result/bench_2/mesh.ply`
- 분류본: `bench_3d/result/bench_2/02_sparse`, `03_dense`, `04_mesh`

분류된 결과의 파일별 용도는 `RESULTS_STRUCTURE.md`에 정리했다.

## fan_1 상세 결과

### 입력 및 프레임

- 원본: `bench_3d/video/fan_1.mov`
- 영상 크기: 22,587,424 bytes
- 영상 길이: 20.435초
- 채택 설정: 5fps, 최대 긴 변 1280px
- 추출 프레임: 102장
- 흐림 판정 프레임: 64장 (62.7%, `Laplacian variance < 100`)
- 중복 프레임 쌍: 6

### Sparse reconstruction

- 생성 모델: 3개
- 채택 모델: `sparse/2`
- 카메라: 1
- 등록 이미지: 35/102
- 등록률: 34.3%
- Sparse 3D points: 1,484
- Observations: 7,347
- 평균 track length: 4.951
- 이미지당 평균 observation: 209.914
- 평균 reprojection error: 0.937px

재투영 오차는 1px 미만이지만 등록률이 낮고 촬영 경로가 21장, 30장, 35장 모델로 분절됐다. 가장 큰 35장 모델만 최종 결과에 사용했다.

### Dense 및 mesh

- Fused points: 227,345
- Mesh vertices: 183,326
- Mesh faces: 337,951
- Point cloud PLY 크기: 약 6.1MB
- Mesh PLY 크기: 약 8.9MB

결과 파일:

- 채택 결과: `bench_3d/result/fan_1/02_sparse`, `03_dense`, `04_mesh`
- 2fps 실패 비교본: `bench_3d/result/fan_1/baseline_2fps`
- 5fps 작업 원본: `bench_3d/workspace/fan_1_fps5`

## 결과 해석

- Sparse points는 카메라 위치와 장면 구조를 계산하는 데 사용한 특징점 기반 3D 점이다.
- Fused points는 각 이미지의 depth map을 결합한 조밀한 컬러 포인트클라우드다.
- Mesh vertices와 faces는 포인트클라우드에서 Poisson surface reconstruction으로 만든 연속 표면의 복잡도를 나타낸다.
- 포인트 수나 버텍스 수가 많다고 항상 품질이 더 좋은 것은 아니다. 영상 선명도, 시점 중첩, 반사면, 움직이는 물체와 촬영 경로도 함께 고려해야 한다.
- `bench_1`은 더 많은 sparse/dense correspondence를 확보해 `bridge_1`보다 조밀한 결과가 생성되었다.
- `bench_2`는 등록률과 reprojection error가 `bench_1`에 근접하지만 dense points와 mesh 복잡도는 `bench_1`보다 낮다.
- `bench_2`는 `bridge_1`보다 sparse points가 138.7%, dense points가 83.5%, mesh faces가 57.3% 많아 더 조밀한 결과를 만들었다.
- `bench_2`는 `bench_1`보다 sparse points가 14.8%, dense points가 36.6%, mesh faces가 54.3% 적다.
- `fan_1`은 5fps로 올려 mesh 생성에는 성공했지만 등록률과 결과 규모가 네 데이터셋 중 가장 낮다. 빠른 이동, 62.7%의 흐림 프레임, 촬영 구간 간 연결 부족이 주요 원인이다.
- 흐림 판정 비율은 `bench_1` 44.8%, `bench_2` 43.4%, `bridge_1` 10.4%, `fan_1` 62.7%다. 포인트 수만으로 시각적 품질을 단정할 수 없으므로 실제 mesh 확인도 병행해야 한다.
