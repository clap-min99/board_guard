# PCB/센서 불량 검사 시스템 - 사용 가이드(YOLO)

## 1. 받아야 할 파일

| 파일 | 설명 |
|---|---|
| `best.pt` | 학습된 YOLO Classification 모델 (원본) |
| `PCB_BG_full.py` | 실행할 메인 스크립트 (Flask 웹 대시보드) |
| `get_detections_demo.py` | 판정 + 위치정보 계산 함수 (`PCB_BG_full.py`가 자동으로 불러다 씀) |

### 폴더에 이렇게 놓으면 됨

```
프로젝트폴더/
├── PCB_BG_full.py
├── get_detections_demo.py
├── best.pt
├── best.onnx          ← 아래 2번에서 직접 만들 파일
└── model_cls.engine   ← 아래 2번에서 직접 만들 파일
```

**3개 파일(`PCB_BG_full.py`, `get_detections_demo.py`, `best.pt`)을 같은 폴더에 넣어주세요.** `.onnx`, `.engine` 파일은 각자 컴퓨터/Jetson에서 직접 변환해서 만들어야 합니다 (아래 2번 참고).

---

## 2. `.pt` → `.onnx` → `.engine` 변환 방법 (VS Code 터미널에서)

### 2-1. 필요한 패키지 확인 (한 번만)

```bash
pip install ultralytics --break-system-packages
```

### 2-2. `.pt` → `.onnx` 변환

VS Code 터미널에서, `best.pt`가 있는 폴더로 이동한 뒤:

```bash
yolo export model=best.pt format=onnx opset=18 simplify=True
```

정상적으로 되면 같은 폴더에 **`best.onnx`** 파일이 생깁니다.

> 만약 `yolo` 명령어가 안 먹히면, 파이썬으로 직접 실행해도 됩니다:
> ```bash
> python3 -c "from ultralytics import YOLO; YOLO('best.pt').export(format='onnx', opset=18, simplify=True)"
> ```

### 2-3. `.onnx` → `.engine` 변환 (TensorRT)

```bash
trtexec --onnx=best.onnx --saveEngine=model_cls.engine --fp16
```

**이 한 줄을 통째로 복사해서 터미널에 붙여넣으세요** (직접 타이핑하면 스페이스/등호가 틀어지기 쉽습니다).

변환이 끝나면 마지막 줄에 아래처럼 떠야 정상입니다:
```
&&&& PASSED TensorRT.trtexec [TensorRT v...] # trtexec ...
```

> 만약 에러가 나면, 아래처럼 입력 크기를 명시해서 다시 시도하세요:
> ```bash
> trtexec --onnx=best.onnx --saveEngine=model_cls.engine --fp16 --minShapes=images:1x3x224x224 --optShapes=images:1x3x224x224 --maxShapes=images:1x3x224x224
> ```

### 2-4. 결과 확인

```bash
ls model_cls.engine
```

파일이 보이면 변환 완료입니다.

---

## 3. `get_detections_demo.py` 설정 확인

이 파일 안의 두 경로가 실제 파일명과 일치하는지 확인해주세요:

```python
CLS_ENGINE_PATH = "model_cls.engine"   # 2번에서 만든 파일
CLS_PT_PATH = "best.pt"                # 받은 원본 파일
```

파일명이 다르면 이 두 줄만 실제 이름에 맞게 고치면 됩니다.

---

## 4. 실행 방법

### 4-1. 필요한 패키지 설치 (한 번만)

```bash
pip install ultralytics opencv-python flask torch --break-system-packages
```

### 4-2. 카메라 주소 설정

`PCB_BG_full.py` 안에서 이 줄을 찾아 실제 카메라 주소로 바꿔주세요:

```python
CAMERA_URL = "http://10.116.224.98:8080/video"   # ⚠️ 실제 폰 IP Webcam 주소로 교체
```

(폰에 IP Webcam 앱을 켜고, 앱 화면에 뜨는 주소를 그대로 넣으면 됩니다. USB 테더링은 재연결할 때마다 주소가 바뀔 수 있으니 매번 확인 필요합니다.)

### 4-3. 실행

```bash
python PCB_BG_full.py
```

터미널에 아래처럼 뜨면 정상 실행된 것입니다:
```
[AnomalyTRT 등 모델 로딩 로그...]
 * Running on all addresses (0.0.0.0)
```

---

## 5. 결과 확인 (브라우저)

같은 네트워크에 있는 PC/폰 브라우저에서:

```
http://<실행한 컴퓨터의 IP>:5000
```

(Jetson이나 PC의 IP는 터미널에서 `hostname -I`로 확인 가능)

화면에서 확인할 수 있는 것:
- 카메라 실시간 영상
- **NORMAL**(초록) / **DEFECT**(빨강) 판정 + 신뢰도(confidence)
- 불량일 경우, 어느 부위가 문제인지 **빨간 박스**로 표시
- **사진 저장** 버튼으로 현재 화면 캡처 가능

---

## 6. 자주 발생하는 문제

| 증상 | 원인 / 해결 |
|---|---|
| `ModuleNotFoundError: No module named 'ultralytics'` | `pip install ultralytics --break-system-packages` 실행 |
| `FileNotFoundError: model_cls.engine` | 2번 변환 과정을 아직 안 했거나, 파일 위치가 다름 |
| 카메라 화면이 안 뜸 | `CAMERA_URL`이 최신 주소인지 확인 (`curl http://주소:8080`으로 테스트) |
| `input size ... not equal to max model size` | Classification 모델은 224x224 고정이므로, 추론 시 `imgsz=224`가 빠지지 않았는지 확인 |
| 화면에서 브라우저 접속이 안 됨 | 방화벽/네트워크 확인, `http://` 뒤에 정확한 IP:5000 입력했는지 확인 |

---

## 7. 참고 - `get_detections()` 함수 반환값

다른 코드에서 이 함수를 가져다 쓸 경우:

```python
from get_detections_demo import get_detections

cls, detail, object_box, bounding_box = get_detections(frame)
```

| 반환값 | 타입 | 의미 |
|---|---|---|
| `cls` | str | `"normal"` 또는 `"defect"` |
| `detail` | float | 신뢰도 (0~1) |
| `object_box` | tuple 또는 None | PCB 전체 영역 (x1, y1, x2, y2) |
| `bounding_box` | tuple 또는 None | 불량 부위 영역 (x1, y1, x2, y2), 정상이면 None |
