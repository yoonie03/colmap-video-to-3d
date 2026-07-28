# COLMAP Video-to-3D Pipeline

## Overview

이 프로젝트는 Ubuntu 24.04 + NVIDIA GPU 환경에서 COLMAP CUDA 빌드를 설치하고, 비디오 입력으로부터 프레임을 추출하여 3D 재구성까지 자동으로 처리하는 스크립트 모음을 제공합니다.

## 프로젝트 구조

- `scripts/`
  - `check_environment.sh` - 시스템 및 CUDA/COLMAP 환경 점검
  - `install_cuda_toolkit.sh` - CUDA Toolkit 설치 스크립트
  - `install_colmap_cuda.sh` - COLMAP CUDA 빌드 및 설치 스크립트
  - `extract_video_frames.sh` - FFmpeg 기반 프레임 추출
  - `run_video_to_3d.sh` - 영상부터 3D 재구성까지 파이프라인 실행
  - `frame_quality_check.py` - 프레임 품질 검사

## 사용법

1. 환경 점검

```bash
bash scripts/check_environment.sh
```

2. CUDA Toolkit 설치

```bash
bash scripts/install_cuda_toolkit.sh
```

3. COLMAP CUDA 빌드 및 설치

```bash
bash scripts/install_colmap_cuda.sh
```

4. 비디오를 3D로 변환

```bash
bash scripts/run_video_to_3d.sh \
  --video ~/Developer/bench_3d/video/bench_1.mov \
  --project-name bench_1 \
  --output-root ~/Developer/bench_3d \
  --fps 2 \
  --max-size 1280 \
  --quality medium
```

## 옵션

- `--fps` : 초당 추출 프레임 수
- `--frame-step` : N프레임마다 한 장만 추출
- `--max-size` : 추출 이미지 최대 긴 변 크기
- `--quality` : low / medium / high
- `--sparse-only` : Sparse reconstruction까지만 실행
- `--force` : 기존 결과 덮어쓰기
- `--resume` : 완료된 단계 건너뛰기
- `--keep-frames` : 추출한 프레임 유지
- `--clean-temp` : 임시 작업 공간 삭제

## 노트

- `run_video_to_3d.sh`는 `extract_video_frames.sh`를 호출하고, `colmap`을 사용해 feature extraction, matching, sparse reconstruction, dense reconstruction, point cloud/mesh 생성을 수행합니다.
- `frame_quality_check.py`는 Laplacian variance 기반 흐림 검사와 인접 프레임 해밍 거리 기반 중복 감지를 수행합니다.
