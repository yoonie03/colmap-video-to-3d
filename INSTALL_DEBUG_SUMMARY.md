# COLMAP 설치 및 디버그 진행 기록

## 목적
Ubuntu 24.04 + NVIDIA GPU 환경에서 COLMAP CUDA 빌드를 설치하고, 비디오 입력을 3D 재구성으로 변환하는 파이프라인을 완성하기 위한 작업 기록입니다.

---

## 환경
- OS: Ubuntu 24.04
- GPU: NVIDIA RTX 5070 Ti
- CUDA: 13.3
- COLMAP 버전: 4.2.0.dev0
- 설치 경로: `/usr/local/bin/colmap`

---

## 진행한 작업
1. `scripts/check_environment.sh`로 기본 커맨드 및 CUDA/COLMAP 환경 점검 준비
2. `scripts/install_cuda_toolkit.sh`에 CUDA 툴킷 및 `ffmpeg` 설치 명령 추가
3. `scripts/install_colmap_cuda.sh`를 작성/수정하여 COLMAP CUDA 빌드 및 설치 자동화
4. `scripts/extract_video_frames.sh` 작성 및 프레임 추출 문제 수정
5. `scripts/run_video_to_3d.sh` 작성하여 비디오 입력 → 프레임 추출 → COLMAP sparse/dense/mesh 파이프라인 구성
6. `scripts/frame_quality_check.py` 추가로 추출 프레임 품질 점검 기능 마련
7. `bench_3d/` 구조 생성 및 테스트용 입력/출력 디렉터리 준비

---

## 발생한 에러 및 해결

### 1. 기본 도구 미설치
- 에러: `cmake`, `ninja`, `ffmpeg`, `git`, `colmap` 등이 존재하지 않음
- 원인: 초기 시스템이 COLMAP 빌드/실행에 필요한 개발 툴과 미디어 도구를 갖추지 않음
- 해결:
  - `cmake`, `ninja-build`, `git`, `ffmpeg` 등 패키지 설치
  - `colmap`이 설치되지 않은 상태에서 `scripts/install_colmap_cuda.sh` 실행 전 환경 정비

### 2. COLMAP CMake 구성 실패 — 의존성 누락
- 에러: Boost Graph, OpenImageIO, Ceres, Qt5Svg, Metis, OpenCV 등의 라이브러리가 누락되어 COLMAP CMake 구성 중단
- 원인: COLMAP 4.2.0.dev0 CUDA 빌드에는 여러 시스템 개발 패키지가 필요함
- 해결:
  - `libboost-graph-dev`
  - `libopenimageio-dev`, `openimageio-tools`
  - `libceres-dev`
  - `libqt5svg5-dev`
  - `libmetis-dev`
  - `libopencv-dev`

### 3. CUDA GPU 빌드 관련 경고
- 에러: Blackwell GPU(sm_100+) 관련 NVCC 버그 경고
- 원인: NVIDIA Blackwell 아키텍처에서 PTX로 JIT 컴파일을 사용하도록 COLMAP 빌드 스크립트가 경고를 표시함
- 해결: 경고는 빌드 자체를 막지 않았고, COLMAP이 `sm_90-virtual (PTX)` 모드로 정상 빌드됨

### 4. COLMAP 설치 후 검증
- 이상 증상: `colmap` 실행 불가 또는 GUI 명령 실패 가능성
- 해결:
  - 빌드 후 `ninja install`로 `/usr/local/bin/colmap` 설치
  - `colmap --help` 및 `colmap gui` 명령을 실행하여 설치와 GUI 명령 동작 확인

---

## 획득한 스킬

- Ubuntu 기반 COLMAP CUDA 빌드 의존성 분석 및 해결
- CMake + Ninja 빌드 로그 해석
- NVIDIA CUDA 아키텍처 관련 경고 파악
- Bash 스크립트로 복잡한 파이프라인 자동화
- FFmpeg를 이용한 비디오 프레임 추출 스크립팅
- COLMAP 명령 기반 feature extraction, matcher, mapper, dense reconstruction, fusion, poisson mesh 생성 흐름 구성
- 실험적 프로젝트 구조화 및 재현 가능한 입력/출력 워크플로우 설계

---

## 앞으로 할 일
- 실제 비디오 파일로 `scripts/run_video_to_3d.sh` 실행하여 end-to-end 검증
- 오류 발생 시 해당 내용을 이 파일에 추가
- `frame_quality_check.py`를 실제 프레임에 적용하여 품질 개선 루틴 추가

---

## 파일 업데이트 규칙
- 새로운 에러/버그 발견 시 `발생한 에러 및 해결` 섹션에 추가
- 파이프라인 개선, 옵션 변경, 스크립트 수정 내용도 이 파일에 기록
- 획득한 스킬은 새 기술을 익힐 때마다 갱신
