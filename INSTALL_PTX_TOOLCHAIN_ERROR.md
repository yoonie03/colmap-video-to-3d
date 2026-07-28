# COLMAP PTX / CUDA Toolchain 오류 보고서

날짜: 2026-07-29

요약:
- 발생한 오류: "the provided PTX was compiled with an unsupported toolchain." (COLMAP 내부 `patch_match_cuda.cu` 실행 중)
- 영향: `colmap patch_match_stereo`가 GPU에서 실행 중에 반복적으로 실패하여 dense reconstruction이 중단되었고, 결과물(`fused.ply`, `mesh.ply`)이 생성되지 않음.

상황 및 재현 방법:
1. COLMAP을 소스에서 CUDA 활성화로 빌드(의도: GPU 가속 유지). 빌드 시 다음과 같은 CMake 플래그를 시도함:
   - `-DCMAKE_CUDA_HOST_COMPILER=/usr/bin/gcc-13`
   - `-DCMAKE_CUDA_ARCHITECTURES=90-virtual`

2. 파이프라인(예시 재현 명령):
```
cd /home/yoonie/Desktop/colmap
DENSE_DIR=bench_3d/workspace/bench_1/dense
IMAGES_DIR=bench_3d/images/bench_1
SPARSE_DIR=bench_3d/workspace/bench_1/sparse
RESULT_DIR=bench_3d/result/bench_1

colmap image_undistorter --image_path "$IMAGES_DIR" --input_path "$SPARSE_DIR/0" --output_path "$DENSE_DIR" --output_type COLMAP --max_image_size 1280
colmap patch_match_stereo --workspace_path "$DENSE_DIR" --workspace_format COLMAP --PatchMatchStereo.geom_consistency true --PatchMatchStereo.gpu_index 0
colmap stereo_fusion --workspace_path "$DENSE_DIR" --workspace_format COLMAP --input_type geometric --output_path "$DENSE_DIR/fused.ply"
colmap poisson_mesher --input_path "$DENSE_DIR/fused.ply" --output_path "$RESULT_DIR/mesh.ply"
```

오류 스니펫 (로그에서 발췌):
```
[cudacc.cc:59] CUDA error at .../src/colmap/mvs/patch_match_cuda.cu:1682 - the provided PTX was compiled with an unsupported toolchain.
... (반복) ...
*** Aborted at 1785257495 (unix time) ...
Aborted (core dumped)
```

관련 로그 파일 / 위치:
- COLMAP 실행 출력(터미널 캡처): `/home/yoonie/.config/Code/copilot-terminal-output/copilot-terminal-output-61a94125-d4a4-40fd-96b6-61e228cb85de.txt`
- 빌드 소스 경로: `/home/yoonie/Developer/tools/colmap` (빌드/소스가 이 위치에 있음)

분석 및 원인 추정:
- 메시지는 PTX(컴파일된 CUDA 중간 코드)가 현재 런타임/드라이버에서 지원하지 않는 툴체인으로 생성되었음을 의미합니다.
- 가능한 원인:
  - `nvcc`가 사용하는 호스트 컴파일러(gcc)와 시스템의 런타임/드라이버 조합 간 불일치
  - NVCC가 생성한 PTX 아키텍처/컴파일 옵션이 GPU 드라이버 또는 CUDA 런타임과 호환되지 않음
  - 빌드 중 캐시된 오래된 PTX가 남아있거나 CMake 설정이 일부 모듈에 적용되지 않음

이미 시도한 조치:
- `-DCMAKE_CUDA_HOST_COMPILER=/usr/bin/gcc-13` 설정으로 재빌드 시도(사용자 환경에 `gcc-13` 존재)
- `-DCMAKE_CUDA_ARCHITECTURES=90-virtual` 설정 시도(Blackwell 계열 CUDA 아키텍처 대응)

권장되는 추가 조치(우선순위 순):
1. 빌드 디렉터리 완전 삭제 후 클린 빌드(이미 시도됨 — 반복 권장 시 `cmake` 캐시 검사):
   - `rm -rf build && mkdir build && cd build && cmake .. [flags] && ninja`  
2. `nvcc`와 드라이버/CUDA 런타임 버전 정합성 확인:
   - `nvcc --version`과 `nvidia-smi`의 CUDA 버전/드라이버 확인
3. 다른 `CMAKE_CUDA_HOST_COMPILER` 후보 시도 (예: `/usr/bin/gcc-12` 등), 또는 호환되는 `gcc` 버전으로 재빌드
4. `CMAKE_CUDA_FLAGS` 또는 `-gencode` 옵션으로 PTX 타겟을 명시적으로 설정해 재빌드
5. 빠른 복구가 필요하면 CPU-only 빌드로 전환해 output을 생성:
   - `cmake -DCUDA_ENABLED=OFF .. && ninja install` (GPU는 느리지만 확실하게 동작)

결론:
- 현재 상태에서는 GPU용 MVS 모듈에서 PTX/toolchain 불일치로 충돌합니다. 다음 단계로 원하는 방향을 알려주시면(추가 재빌드 시도 또는 CPU fallback) 제가 바로 조치하겠습니다.
