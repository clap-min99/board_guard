# PCB 이상탐지 검사 시스템 (boardguard)

PatchCore(비지도 이상탐지) 기반 PCB 실시간 불량 검사. Jetson Orin Nano + TensorRT로 배포.

## 왜 모델 파일이 git에 없는지

- **`.engine` 파일은 git에 아예 올리지 않습니다.** TensorRT 엔진은 빌드한 Jetson의 GPU/TensorRT/JetPack 버전에 종속적이라, 다른 장비에서 만든 `.engine`은 다른 장비에서 그대로 안 돌아갈 수 있습니다. **각자의 Jetson에서 직접 변환**해야 합니다.
- **`.onnx` 파일도 git에는 안 올립니다** (용량 문제). 대신 아래 "모델 받기" 방법 중 하나로 받으세요.

## 저장소 구조

```
Patchcore/
├── trt_module.py              # TensorRT 엔진 추론 래퍼 (multi-output 지원)
├── pcb_inspector.py       # 앞면/뒷면 검사 버튼 UI 앱 (메인 실행 파일)
├── capture_dataset.py         # 학습용 정상/불량 사진 촬영 스크립트
├── capture_empty_reference.py # MISSING 판별용 빈 배경 기준 사진 촬영
├── patchcore_hs04_front.ipynb  # 학습 노트북 (Colab)
├── patchcore_hs04_back.ipynb  # 학습 노트북 (Colab)
├── .gitignore
└── README.md
```

## 1. 모델 받기

### 방법 A — 이미 학습된 모델 다운로드 (가장 빠름, 권장)

Google Drive 공유 폴더에서 아래 두 파일을 받으세요.

- `model_front.onnx` (앞면용)
- `model_back.onnx` (뒷면용)

📎 다운로드 링크: **[다운링크(권한요청필요)](https://drive.google.com/drive/folders/1FBJts0ZAV7pYvoouLwHX4gdjK-AcVLNY?usp=drive_link)**

받은 `.onnx` 파일을 이 저장소 루트(`Patchcore/`)에 그대로 둡니다.

### 방법 B — 직접 재학습 (데이터셋부터 새로 모을 경우)

1. `capture_dataset.py`로 정상/불량 사진 촬영 (사용법은 스크립트 상단 docstring 참고)
2. `pcb_anomaly_detection_colab.ipynb`를 Colab에서 열어 `Folder` datamodule에 촬영한 데이터 경로 연결
3. `Patchcore(backbone="resnet18", precision="float16")`로 학습
4. `engine.export(..., export_type=ExportType.ONNX)`로 `.onnx` 추출

## 2. ONNX → TensorRT 엔진 변환 (Jetson에서, 각자 필수로 실행)

```bash
pip install onnx  # 아직 없으면

trtexec --onnx=model_front.onnx \
        --saveEngine=model_01.engine \
        --fp16 \
        --memPoolSize=workspace:4096MiB \
        --shapes=input:1x3x256x256

trtexec --onnx=model_back.onnx \
        --saveEngine=model_back.engine \
        --fp16 \
        --memPoolSize=workspace:4096MiB \
        --shapes=input:1x3x256x256
```

- `--shapes=input:1x3x256x256`: 반드시 명시해야 합니다. 생략하면 입력 shape을 `1x3x1x1`로 잘못 잡아서 빌드가 깨집니다.
- 맨 마지막에 `PASSED`가 뜨는지 확인하세요.
- **TensorRT 버전에 따라 `Greater` 노드 관련 빌드 에러(`insufficient workspace`)가 날 수 있습니다.** 이 경우 아래 스니펫으로 post-processing 노드를 제거한 ONNX를 다시 만들어서 변환하세요.

```python
import onnx.utils

onnx.utils.extract_model(
    input_path="model_01.onnx",
    output_path="model_01_no_postproc.onnx",
    input_names=["input"],
    output_names=["pred_score", "anomaly_map"],
)
```
(이 경우 `pred_label`/`pred_mask`가 출력에서 빠지므로, `pcb_inspector_app.py`가 `anomaly_map`을 threshold로 직접 이진화해서 대체합니다. 코드에 이미 fallback 로직이 들어있습니다.)

## 3. MISSING(보드 없음) 판별용 기준 사진 촬영

카메라/조명 환경마다 다시 찍어야 합니다 (다른 사람 걸 그대로 쓰면 안 됨).

```bash
python capture_empty_reference.py
```
조명 박스를 완전히 비운 상태에서 `space`로 저장 → `empty_reference.jpg` 생성.

## 4. 실행

```bash
python3 pcb_inspector.py
```

- 실행하면 기본으로 `FRONT CHECK` 모드가 켜진 채 시작합니다.
- 화면 하단 `FRONT CHECK` / `BACK CHECK` 버튼을 클릭하면 그 모드로 전환되어, **매 프레임 계속** 판정합니다 (같은 버튼 다시 클릭 시 대기 상태).
- `q`로 종료.

### 실행 전 확인할 설정값 (`pcb_inspector_app.py` 상단)

```python
FRONT_ENGINE_PATH = "model_01.engine"
BACK_ENGINE_PATH = "model_back.engine"
EMPTY_REFERENCE_PATH = "empty_reference.jpg"
CAMERA_URL = "http://<본인 카메라 IP>:8080/video"   # 실행 전 반드시 확인/수정
FRONT_THRESHOLD = 0.55
BACK_THRESHOLD = 0.4
```

## 5. 인터페이스 (다른 파트에서 가져다 쓸 때)

```python
class, detail, bounding_box = get_detections_front(frame)   # 또는 get_detections_back(frame)
```

| 값 | 타입 | 설명 |
|---|---|---|
| `class` | `str` | `"MISSING"` \| `"PASS"` \| `"FAIL"` |
| `detail` | `float` | MISSING: 배경과의 차이 비율(0~1) / PASS·FAIL: anomaly score(0~1) |
| `bounding_box` | `list[tuple]` | 결함 위치 `[(x1,y1,x2,y2), ...]`. 원본 프레임 픽셀 좌표 기준. MISSING·PASS면 `[]` |

`frame`은 OpenCV BGR 프레임(numpy array)이어야 합니다.

## 알려진 이슈 / 참고사항

- IP Webcam(안드로이드 앱) 사용 시 USB 테더링 재연결마다 IP가 바뀔 수 있습니다. `ip addr | grep -A 2 usb`로 확인 후 `CAMERA_URL` 수정하세요.

- 앞면은 부품이 많아 각도/반사에 따른 score 변동폭이 뒷면보다 큽니다 (그래서 threshold도 앞면이 더 높게 잡혀 있음).

- 각 모델은 학습된 촬영 환경(조명/배경/카메라 거리)에 강하게 의존합니다. 촬영 환경이 크게 바뀌면 재학습이 필요할 수 있습니다.