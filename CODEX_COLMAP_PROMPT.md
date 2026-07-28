# Codex 작업 프롬프트: 영상 입력 기반 COLMAP 3D 복원 파이프라인 구축

## 1. 작업 목적

Ubuntu 24.04 + NVIDIA GPU 환경에서 COLMAP을 CUDA 지원으로 설치하고, 사용자가 영상 파일 하나를 넣으면 다음 과정을 자동으로 수행하도록 프로젝트를 구축하라.

1. 영상 입력
2. FFmpeg로 프레임 추출
3. 특징점 추출
4. 이미지 매칭
5. Sparse reconstruction
6. Dense reconstruction
7. Dense point cloud 생성
8. Poisson mesh 생성
9. 결과 파일 정리 및 검증

최종 목표는 향후 균열 탐지 모델의 결과를 3D 모델 좌표에 표시할 수 있는 기반을 만드는 것이다.

---

## 2. 현재 환경

- 운영체제: Ubuntu 24.04
- GPU: NVIDIA GPU
- NVIDIA 드라이버: nvidia-smi로 확인
- CUDA Toolkit: 설치 필요 또는 설치 상태 확인 필요
- 현재 nvcc --version 실행 시 nvcc: command not found가 나올 수 있음
- IDE: VS Code
- 터미널: Ubuntu Terminal 또는 tmux
- COLMAP: 아직 설치되지 않았거나 CUDA 지원 빌드 필요

확인되지 않은 값을 가정하지 말고 실제 명령을 실행해 상태를 확인한 뒤 진행하라.

---

## 3. 프로젝트 구조

다음 구조를 기준으로 한다.

~/Developer/bench_3d/
├── video/
│   ├── bench_1.mov
│   ├── bench_2.mov
│   └── bridge_1.mov
├── images/
│   ├── bench_1/
│   ├── bench_2/
│   └── bridge_1/
├── workspace/
│   ├── bench_1/
│   ├── bench_2/
│   └── bridge_1/
├── result/
│   ├── bench_1/
│   ├── bench_2/
│   └── bridge_1/
├── scripts/
├── config/
└── README.md

우선 bench_1.mov으로 전체 파이프라인을 검증한다.

---

## 4. Codex가 수행할 작업

### 4.1 환경 점검 스크립트 작성

다음 파일을 작성한다.

scripts/check_environment.sh

확인 항목:

- Ubuntu 버전
- CPU 아키텍처
- GPU 이름
- NVIDIA 드라이버 버전
- nvidia-smi 정상 여부
- nvcc 설치 여부
- CUDA Toolkit 버전
- CUDA 설치 경로
- CMake 버전
- Ninja 버전
- GCC/G++ 버전
- FFmpeg 설치 여부
- COLMAP 설치 여부
- COLMAP CUDA 지원 여부
- 디스크 여유 공간
- GPU 메모리

오류가 있으면 원인을 명확하게 출력하고 필요한 조치를 안내하라.

### 4.2 CUDA Toolkit 설치 스크립트 작성

다음 파일을 작성한다.

scripts/install_cuda_toolkit.sh

요구사항:

- Ubuntu 24.04 기준
- NVIDIA 공식 저장소 사용
- 기존 NVIDIA 드라이버를 불필요하게 덮어쓰지 않음
- CUDA Toolkit만 설치
- /usr/local/cuda 확인
- PATH와 LD_LIBRARY_PATH를 중복 없이 설정
- 설치 후 nvcc --version 검증
- nvidia-smi도 다시 확인
- 드라이버를 변경하지 않았다면 재부팅을 필수라고 단정하지 않음
- 모든 설치 로그 저장

### 4.3 COLMAP CUDA 빌드 스크립트 작성

다음 파일을 작성한다.

scripts/install_colmap_cuda.sh

요구사항:

- 공식 GitHub 저장소 사용
- 의존성 패키지 자동 설치
- CMake + Ninja 사용
- Release 빌드
- CUDA 활성화
- 현재 GPU Compute Capability에 맞는 CUDA architecture 설정
- 소스와 빌드 디렉터리 분리
- 빌드 실패 시 로그 저장
- 설치 후 colmap -h 확인
- colmap gui 실행 가능 여부 확인
- 실제 CUDA 지원 빌드인지 확인

작업 경로 예:

~/Developer/tools/colmap/src/
~/Developer/tools/colmap/build/

### 4.4 영상 직접 입력 기능 구현

사용자가 .mov, .mp4, .avi, .mkv 영상 파일 하나를 입력하면 자동으로 처리하는 스크립트를 작성한다.

생성 파일:

scripts/extract_video_frames.sh
scripts/run_video_to_3d.sh

실행 예:

bash scripts/run_video_to_3d.sh \
  --video ~/Developer/bench_3d/video/bench_1.mov \
  --project-name bench_1 \
  --output-root ~/Developer/bench_3d

지원 옵션:

--video           입력 영상 경로
--project-name    프로젝트 이름
--output-root     프로젝트 루트
--fps             초당 추출 프레임 수, 기본값 2
--frame-step      N프레임마다 한 장 추출
--max-size        추출 이미지 최대 긴 변 크기
--quality         low, medium, high
--sparse-only     Sparse까지만 실행
--force           기존 결과 덮어쓰기
--resume          완료된 단계는 건너뛰고 중단 지점부터 재개
--keep-frames     프레임 유지
--clean-temp      임시 파일 삭제

### 4.5 영상 프레임 추출

FFmpeg를 사용한다.

필수 기능:

- FFmpeg 설치 여부 확인
- 영상 해상도 확인
- 전체 길이 확인
- 원본 FPS 확인
- 지정한 FPS 또는 frame-step 기준으로 프레임 추출
- JPG 품질 설정
- 프레임 파일명 정렬 보장

예상 파일명:

frame_000001.jpg
frame_000002.jpg
frame_000003.jpg

프레임 추출 후 다음을 확인한다.

- 추출 프레임 수
- 너무 적은 프레임인지
- 너무 많은 프레임인지
- 지나치게 유사한 프레임이 많은지
- 흐림이 심한 프레임 비율

가능하면 OpenCV 또는 FFmpeg 기반으로 간단한 품질 검사를 구현한다.

- Laplacian variance 기반 흐림 검사
- 평균 해시 또는 perceptual hash 기반 중복 검사
- 너무 흐리거나 거의 동일한 프레임은 선택적으로 제외
- 제외된 프레임 목록 로그 저장

단, 원본 프레임을 무조건 삭제하지 말고 별도 목록으로 관리하라.

---

## 5. COLMAP 자동 파이프라인

다음 순서로 실행한다.

feature_extractor
→ sequential_matcher
→ mapper
→ image_undistorter
→ patch_match_stereo
→ stereo_fusion
→ poisson_mesher

영상 프레임이므로 기본 matcher는 sequential_matcher를 사용한다.

필수 조건:

- 모든 경로는 공백과 한글에 안전하게 처리
- 입력 영상 및 이미지 폴더 존재 여부 확인
- 이전 결과가 있으면 --force 또는 --resume 처리
- 각 단계 시작·종료 시간 출력
- 단계별 로그 저장
- 중간 실패 시 즉시 종료
- 완료된 단계는 상태 파일로 기록
- Sparse 모델이 여러 개면 등록 이미지 수가 가장 많은 모델 자동 선택
- 최종 결과를 result 폴더로 복사
- 사용한 COLMAP 명령과 옵션을 로그에 기록

---

## 6. 기본 품질 설정

### low

- 빠른 테스트
- 작은 이미지 크기
- 적은 PatchMatch source image 수
- 낮은 GPU 메모리 사용

### medium

- 기본 권장값
- 최대 이미지 크기 약 2000~3000 px
- Sparse 및 Dense 모두 실행
- Poisson mesh 생성

### high

- 원본 또는 큰 이미지 크기
- 더 많은 source image 사용
- 더 긴 처리 시간과 높은 GPU 메모리 사용

처음 실행은 medium으로 한다.

---

## 7. GPU 메모리 부족 대응

GPU 메모리가 부족하면 다음 값을 단계적으로 낮출 수 있게 구현하라.

- 최대 이미지 크기
- PatchMatchStereo source image 수
- PatchMatchStereo window radius
- cache size
- geometric consistency 설정
- 프레임 추출 FPS

OOM이 발생하면 로그를 분석해 자동으로 한 단계 낮은 설정으로 재시도하는 기능을 고려하라.

무한 재시도는 하지 말고 최대 재시도 횟수를 제한하라.

---

## 8. 결과 폴더 구조

최종 결과 예:

~/Developer/bench_3d/result/bench_1/
├── sparse.ply
├── fused.ply
├── meshed-poisson.ply
├── selected_sparse_model.txt
├── summary.txt
└── logs/
    ├── environment.log
    ├── ffmpeg.log
    ├── feature_extractor.log
    ├── sequential_matcher.log
    ├── mapper.log
    ├── image_undistorter.log
    ├── patch_match_stereo.log
    ├── stereo_fusion.log
    └── poisson_mesher.log

중간 작업 폴더:

~/Developer/bench_3d/workspace/bench_1/
├── database.db
├── sparse/
├── dense/
├── state/
└── logs/

추출 프레임:

~/Developer/bench_3d/images/bench_1/

---

## 9. 결과 검증 스크립트

다음 파일을 작성한다.

scripts/verify_colmap_result.sh

확인 항목:

- 입력 영상 존재 여부
- 추출 프레임 수
- 데이터베이스 존재 여부
- 등록된 이미지 수
- Sparse point 수
- Dense point cloud 존재 여부
- Mesh 존재 여부
- 결과 파일 크기
- CUDA 사용 로그
- 실패 단계
- 총 실행 시간

가능하면 다음 형식으로 출력한다.

[COLMAP RESULT]
Video              : bench_1.mov
Frames extracted   : 320
Images registered  : 286
Sparse points      : 154203
Dense point cloud  : OK
Poisson mesh       : OK
CUDA               : ENABLED
Result directory   : ~/Developer/bench_3d/result/bench_1

---

## 10. 향후 균열 표시 확장 구조

현재는 3D 복원까지만 구현하되, 다음 기능을 추가하기 쉽게 구조를 설계한다.

1. 2D 균열 세그멘테이션 결과 입력
2. COLMAP 카메라 내부 파라미터 읽기
3. COLMAP 카메라 자세 읽기
4. 균열 마스크 픽셀을 3D 점군 또는 메시로 투영
5. 3D 모델 위에 균열 위치 표시
6. 균열 ID, 신뢰도, 길이, 폭, 원본 이미지 연결
7. 웹 기반 3D 뷰어 연동

향후 Python에서 COLMAP 결과를 읽기 위해 다음을 고려한다.

pycolmap
COLMAP Python model reader
Open3D
trimesh
Three.js

현재 단계에서는 실제 균열 투영 기능은 구현하지 않아도 되지만, 폴더 구조와 결과 형식은 확장 가능하게 설계하라.

---

## 11. 구현 원칙

- 명령어를 추측하지 말고 현재 설치된 버전의 -h 출력을 확인
- 버전에 따라 옵션 이름이 다르면 자동 감지 또는 명확히 설명
- 공식 COLMAP 및 NVIDIA 문서를 우선 기준으로 사용
- 기존 NVIDIA 드라이버를 함부로 변경하지 않음
- 기존 사용자 데이터를 삭제하지 않음
- 스크립트는 여러 번 실행해도 안전하도록 작성
- 오류를 숨기지 말고 로그와 해결 방법을 제시
- 각 단계는 독립적으로 재실행 가능하게 작성
- Bash 스크립트에는 set -Eeuo pipefail 사용
- 경로는 항상 따옴표로 처리
- 명령 실행 전 입력 검증
- 종료 코드를 정확하게 반환
- 설치와 실행 작업을 분리

---

## 12. 생성할 산출물

다음 파일을 생성하라.

README.md
scripts/check_environment.sh
scripts/install_cuda_toolkit.sh
scripts/install_colmap_cuda.sh
scripts/extract_video_frames.sh
scripts/run_video_to_3d.sh
scripts/run_colmap_pipeline.sh
scripts/verify_colmap_result.sh
config/colmap.env.example
.gitignore

---

## 13. README 작성 내용

README에는 다음을 포함하라.

- 전체 목적
- 설치 순서
- CUDA 확인 방법
- COLMAP CUDA 지원 확인 방법
- 영상 하나로 실행하는 방법
- 이미지 폴더로 직접 실행하는 방법
- 폴더 구조
- 품질 옵션 설명
- resume 및 force 사용법
- 예상 결과 파일
- 대표 오류 해결 방법
- GPU 메모리 부족 대응
- 촬영 시 권장 사항
- 향후 균열 투영 기능 확장 방향

대표 실행 명령:

bash scripts/check_environment.sh

bash scripts/install_cuda_toolkit.sh

bash scripts/install_colmap_cuda.sh

bash scripts/run_video_to_3d.sh \
  --video ~/Developer/bench_3d/video/bench_1.mov \
  --project-name bench_1 \
  --output-root ~/Developer/bench_3d \
  --fps 2 \
  --quality medium

bash scripts/verify_colmap_result.sh \
  --workspace ~/Developer/bench_3d/workspace/bench_1 \
  --result ~/Developer/bench_3d/result/bench_1

---

## 14. 작업 진행 방식

먼저 현재 환경을 점검하라.

다음 항목을 실제로 확인한 뒤 작업을 시작하라.

lsb_release -a
uname -m
nvidia-smi
nvcc --version
cmake --version
ninja --version
ffmpeg -version
colmap -h

설치되지 않은 항목은 오류를 숨기지 말고 명확히 표시하라.

그다음 설치 스크립트와 실행 스크립트를 작성하고, bench_1.mov 기준으로 전체 파이프라인을 테스트하라.

최종적으로 사용자가 영상 파일 하나만 지정하면 프레임 추출부터 Sparse, Dense, Poisson mesh 생성까지 자동으로 수행되게 완성하라.