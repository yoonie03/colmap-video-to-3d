# COLMAP 영상 기반 3D 재구성 사용 가이드

## 무엇을 만드는가

이 프로젝트는 한 물체나 공간을 여러 각도에서 촬영한 영상을 입력받아 다음 결과를 만든다.

1. 영상에서 추출한 이미지 프레임
2. 카메라 위치와 sparse point cloud
3. 조밀한 컬러 point cloud
4. 표면을 가진 triangle mesh

최종 결과 형식은 일반적인 3D 프로그램에서 읽을 수 있는 PLY다.

## 현재 환경의 중요 사항

이 컴퓨터는 RTX 5070 Ti와 CUDA 13.3을 사용하지만 설치된 NVIDIA 드라이버가 CUDA 13.2 수준의 PTX만 직접 지원한다. 또한 COLMAP은 Blackwell GPU의 NVCC 문제를 피하려고 MVS 커널을 PTX로 빌드한다.

따라서 시스템의 `/usr/local/bin/colmap`을 직접 실행하면 다음 오류가 다시 발생할 수 있다.

```text
the provided PTX was compiled with an unsupported toolchain
```

항상 프로젝트의 다음 래퍼를 사용한다.

```bash
cd /home/yoonie/Desktop/colmap
./colmap_cuda13_3.sh -h
```

이 래퍼는 다음을 자동으로 적용한다.

- CUDA 13.3 forward-compat 드라이버 라이브러리
- RTX 5070 Ti용으로 빌드된 COLMAP 실행 파일
- COLMAP의 공식 Blackwell PTX 우회

## 가장 간단한 실행 방법

새 영상을 `bench_3d/video` 아래에 넣고 다음 명령을 실행한다.

```bash
cd /home/yoonie/Desktop/colmap

mkdir -p .local/bin
ln -sfn /home/yoonie/Desktop/colmap/colmap_cuda13_3.sh .local/bin/colmap

PATH=/home/yoonie/Desktop/colmap/.local/bin:$PATH \
bash scripts/run_video_to_3d.sh \
  --video /home/yoonie/Desktop/colmap/bench_3d/video/새영상.MOV \
  --project-name 새프로젝트 \
  --output-root /home/yoonie/Desktop/colmap/bench_3d \
  --fps 2 \
  --max-size 1280 \
  --quality medium \
  --keep-frames
```

예를 들어 `bench_2`를 처리하려면:

```bash
cd /home/yoonie/Desktop/colmap

PATH=/home/yoonie/Desktop/colmap/.local/bin:$PATH \
bash scripts/run_video_to_3d.sh \
  --video /home/yoonie/Desktop/colmap/bench_3d/video/bench_2.MOV \
  --project-name bench_2 \
  --output-root /home/yoonie/Desktop/colmap/bench_3d \
  --fps 2 \
  --max-size 1280 \
  --quality medium \
  --keep-frames
```

## 주요 옵션

| 옵션 | 의미 | 권장값 |
|---|---|---|
| `--fps` | 영상 1초당 추출할 프레임 수 | 일반 촬영 2, 빠른 이동 3~5 |
| `--max-size` | 이미지 긴 변의 최대 픽셀 | 속도 우선 1280, 품질 우선 1920 |
| `--quality` | JPEG 추출 품질 | `medium` 또는 `high` |
| `--keep-frames` | 처리 후 추출 프레임 보존 | 재실행할 때 유용하므로 권장 |
| `--resume` | 완료된 단계 재사용 | 중단 후 재개 시 사용 |
| `--sparse-only` | sparse까지만 실행 | 촬영 상태를 빠르게 확인할 때 사용 |
| `--force` | 기존 프로젝트를 지우고 재실행 | 기존 결과가 필요 없을 때만 사용 |

`--force`는 기존 workspace와 result를 삭제하므로 결과 백업 후 사용해야 한다.

## 결과 디렉터리

프로젝트 이름이 `bridge_1`이라면 다음 구조로 생성된다.

```text
bench_3d/
├── images/bridge_1/
│   ├── frame_000001.jpg
│   └── frame_quality_report.txt
├── workspace/bridge_1/
│   ├── database.db
│   ├── sparse/0/
│   └── dense/
│       ├── stereo/
│       └── fused.ply
└── result/bridge_1/
    ├── point_cloud.ply
    └── mesh.ply
```

- `sparse/0`: 카메라 자세와 sparse point cloud
- `dense/fused.ply`: dense point cloud 원본
- `result/.../point_cloud.ply`: 배포하기 편하도록 복사한 dense point cloud
- `result/.../mesh.ply`: 최종 triangle mesh

## 결과 열기

이 프로젝트에는 sudo 없이 로컬 설치한 MeshLab이 있다.

### 최종 mesh 열기

```bash
env \
  LD_LIBRARY_PATH=/home/yoonie/Desktop/colmap/.local/meshlab/root/usr/lib/x86_64-linux-gnu \
  QT_PLUGIN_PATH=/usr/lib/x86_64-linux-gnu/qt5/plugins \
  /home/yoonie/Desktop/colmap/.local/meshlab/root/usr/bin/meshlab \
  /home/yoonie/Desktop/colmap/bench_3d/result/bridge_1/mesh.ply
```

### 포인트클라우드 열기

```bash
env \
  LD_LIBRARY_PATH=/home/yoonie/Desktop/colmap/.local/meshlab/root/usr/lib/x86_64-linux-gnu \
  QT_PLUGIN_PATH=/usr/lib/x86_64-linux-gnu/qt5/plugins \
  /home/yoonie/Desktop/colmap/.local/meshlab/root/usr/bin/meshlab \
  /home/yoonie/Desktop/colmap/bench_3d/result/bridge_1/point_cloud.ply
```

MeshLab에서 마우스 드래그로 회전하고 휠로 확대·축소할 수 있다.

## 3D 모델이 만들어지는 원리

전체 흐름은 다음과 같다.

```text
영상
  → 프레임 추출
  → 특징점 검출 및 매칭
  → SfM 카메라 자세 계산
  → sparse point cloud
  → 이미지별 depth/normal 계산
  → depth map fusion
  → dense point cloud
  → Poisson surface reconstruction
  → triangle mesh
```

### 1. 프레임 추출

FFmpeg가 동영상에서 일정 간격으로 JPEG 이미지를 추출한다. 2fps라면 1초에 두 장을 사용한다. 프레임이 너무 적으면 시점 사이 공통 영역이 부족하고, 너무 많으면 처리 시간과 중복 데이터가 증가한다.

### 2. 특징점 검출

COLMAP은 각 이미지에서 모서리나 질감처럼 다시 찾기 쉬운 SIFT 특징점을 검출한다. 하늘, 단색 벽, 유리와 반사면은 안정적인 특징점이 적다.

### 3. 특징점 매칭

서로 다른 프레임에서 동일한 실제 지점을 나타내는 특징점을 연결한다. 현재 스크립트는 모든 이미지 조합을 검사하는 exhaustive matcher를 사용한다.

### 4. Structure from Motion

SfM은 여러 이미지의 대응점을 이용해 다음 값을 함께 추정한다.

- 각 프레임을 촬영한 카메라의 위치와 방향
- 카메라 내부 파라미터
- 특징점의 3D 위치

이 단계의 결과가 sparse point cloud다. 카메라 자세를 계산하는 뼈대 역할을 하므로 sparse 점 자체가 최종 표면은 아니다.

### 5. Multi-View Stereo

PatchMatch Stereo는 sparse 카메라 정보를 기준으로 각 픽셀의 깊이와 표면 법선을 추정한다. 여러 시점에서 같은 깊이가 관측되는지 geometric consistency 검사도 수행한다.

이 단계가 GPU 연산량과 전체 처리 시간의 대부분을 차지한다.

### 6. Stereo fusion

각 이미지에서 계산한 depth map을 하나의 좌표계로 합친다. 서로 일치하는 관측만 남기면서 색상, 위치, normal을 가진 dense point cloud를 만든다.

### 7. Poisson meshing

Poisson surface reconstruction은 포인트 위치와 normal을 이용해 빈 공간과 물체 내부를 구분하는 연속 표면을 추정한다. 이 표면을 삼각형으로 나눈 결과가 `mesh.ply`다.

## 좋은 촬영 방법

- 물체나 공간 주위를 천천히 이동한다.
- 앞 프레임과 다음 프레임이 60~80% 정도 겹치게 촬영한다.
- 갑자기 방향을 바꾸거나 빠르게 흔들지 않는다.
- 자동 노출이 크게 변하지 않도록 한다.
- 물체의 모든 면을 여러 높이와 각도에서 촬영한다.
- 유리, 거울, 물, 움직이는 나뭇잎이나 사람은 가능한 한 피한다.
- 가까운 물체만 촬영할 때는 배경보다 대상에 초점이 유지되도록 한다.
- 디지털 줌은 사용하지 않는다.

## 결과 품질을 판단하는 방법

- 등록 이미지 비율이 높을수록 촬영 경로가 잘 연결된 것이다.
- 평균 reprojection error는 일반적으로 1px 이하이면 양호하다.
- fusion point가 0이면 depth map 또는 filtering 과정에 문제가 있는 것이다.
- 포인트클라우드가 여러 조각으로 갈라지면 시점 중첩이나 특징점이 부족한 경우가 많다.
- mesh의 얇은 막, 구멍, 떠 있는 조각은 반사면, 움직임, 배경 점 또는 잘못된 depth 때문이다.

## 문제 해결

### PTX toolchain 오류

반드시 다음 래퍼를 통해 실행한다.

```bash
./colmap_cuda13_3.sh patch_match_stereo ...
```

### 중단 후 재개

```bash
PATH=/home/yoonie/Desktop/colmap/.local/bin:$PATH \
bash scripts/run_video_to_3d.sh \
  --video 영상경로 \
  --project-name 프로젝트명 \
  --output-root /home/yoonie/Desktop/colmap/bench_3d \
  --fps 2 --max-size 1280 --quality medium \
  --keep-frames --resume
```

### Sparse 등록률이 낮을 때

- fps를 3~5로 올린다.
- 흔들리거나 흐린 구간을 제거한다.
- 대상 주변을 한 방향으로 연속 촬영한다.
- 질감이 거의 없는 물체에는 임시 마커나 주변 특징을 추가한다.

### 처리 속도를 높이고 싶을 때

- `--max-size 960` 또는 `1280`을 사용한다.
- fps를 낮춘다.
- 먼저 `--sparse-only`로 촬영 품질을 검증한다.
- 불필요하거나 심하게 흐린 프레임을 제거한다.

## 현재 결과

프로젝트별 정확한 통계와 처리 시간은 `COLMAP_RESULTS.md`를 참고한다.
