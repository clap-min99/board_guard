# BoardGuard 전체 실행 방법(manual)

> GitHub: https://github.com/clap-min99/board_guard/tree/master
> 저장소 루트 기준:
> `AI_UI/Patchcore/` = PatchCore 검사 앱 전체(실행 스크립트 + `.onnx` + `.engine` 포함) /
> `code/` = STM32F411RE 펌웨어(mcu_m4 브랜치 내용)

전체 흐름
① 휴대폰 IP 카메라 세팅(상자 기구물 위)

② Jetson에서 onnx→engine 변환 후 AI_UI/Patchcore 실행

③ code 폴더 빌드·플래시

④ Jetson↔M4 GPIO 연결 후 전체 기동

---

## 1. 휴대폰 카메라 세팅 (USB 테더링)

Jetson이 폰 카메라 화면을 네트워크 스트림으로 받아오는 구조이므로 폰을 IP 카메라로 켜두고 USB 테더링으로 Jetson과 묶어야 함.

1. 폰에 **IP Webcam** 앱 설치 (Android, Play스토어)
2. 폰 설정 → 네트워크 및 인터넷 → 핫스팟 및 테더링 → **USB 테더링 ON**
   - Jetson과 폰을 USB 케이블로 연결한 상태에서 켜야 함
3. Jetson에서 폰이 잡은 USB 네트워크 인터페이스의 IP 확인

   ```bash
   ip addr | grep -A 2 usb
   ```

   `usb0` 같은 인터페이스에 잡힌 `inet` 주소(예: `192.168.42.129`)가 폰 IP대역 쪽 Jetson IP. 폰 쪽 IP는 보통 `.129` 대신 `.1` 이나 IP Webcam 앱 실행화면에 직접 떠 있는 주소로 확인하는 게 제일 정확함.
4. IP Webcam 앱에서 **서버 시작(Start server)** 누르면 앱 화면에 `http://<폰IP>:8080` 형태 주소가 뜸 → 이 주소를 이후 `pcb_inspector.py`의 `CAMERA_URL`에 씀 (`/video` 붙여서)

**주의**: USB 테더링을 껐다 켤 때마다 폰 IP가 바뀔 수 있음. 실행 전마다 `ip addr | grep -A 2 usb`로 재확인하고 `CAMERA_URL`을 그때그때 맞춰줘야 함.

---

## 2. AI_UI/Patchcore (Jetson, PatchCore 추론)

### 2-1. 폴더 확인

`AI_UI/Patchcore/` 안에 아래가 다 있어야 정상:

```
AI_UI/Patchcore/
├── pcb_inspector.py         # 메인 실행 파일
├── classify_by_embedding.py # 불량 유형 분류
├── embedding_utils.py
├── database.py               # 판정 결과 DB 기록
├── drawing.py                 # 결과 시각화
├── trt_module.py             # TensorRT 추론 래퍼
├── web.py                     # Flask 대시보드
├── front_reference.jpg / back_reference.jpg   # MISSING 판별 기준
├── front_regions.json / back_regions.json     # 결함 위치 영역 정의
├── model_front.onnx / model_back.onnx         # (직접 넣어둔 모델)
└── model_front.engine / model_back.engine     # (직접 넣어둔 엔진, 없으면 2-3에서 생성)
```

### 2-2. 파이썬 환경 준비 (Jetson)

```bash
pip install onnx opencv-python flask pycuda
```
(TensorRT, PyCUDA는 JetPack에 기본 포함된 버전을 쓰는 게 안전 — 별도로 pip 버전 깔면 충돌 가능)

### 2-3. ONNX → TensorRT 엔진 변환 (Jetson에서 필수로 직접 수행)

`.engine` 파일은 빌드한 Jetson의 GPU/TensorRT/JetPack 버전에 종속적이라, 다른 장비에서 만든 `.engine`을 그대로 가져오면 안 돌아갈 수 있음. 지금 Jetson에서 아래처럼 직접 변환:

```bash
cd AI_UI/Patchcore

trtexec --onnx=model_front.onnx \
        --saveEngine=model_front.engine \
        --fp16 \
        --memPoolSize=workspace:4096MiB \
        --shapes=input:1x3x256x256

trtexec --onnx=model_back.onnx \
        --saveEngine=model_back.engine \
        --fp16 \
        --memPoolSize=workspace:4096MiB \
        --shapes=input:1x3x256x256
```

- `--shapes=input:1x3x256x256`은 **반드시 명시**. 생략하면 입력 shape을 `1x3x1x1`로 잘못 잡아서 빌드가 깨짐.
- 로그 맨 끝에 `PASSED` 뜨는지 확인.

### 2-4. MISSING(보드 없음) 판별용 기준 사진 재촬영

카메라/조명 환경이 우리 셋업이랑 다르면 `front_reference.jpg` / `back_reference.jpg`를 다시 찍어야 정확함:

```bash
python capture_empty_reference.py
```
검사 구간을 완전히 비운 상태에서 `space`로 저장.

### 2-5. 실행 전 설정값 확인 (`pcb_inspector.py` 상단)

```python
FRONT_ENGINE_PATH = "model_front_03.engine"
BACK_ENGINE_PATH  = "model_back_03.engine"
EMPTY_REFERENCE_PATH = "empty_reference.jpg"
CAMERA_URL = "http://<1번에서 확인한 폰 IP>:8080/video"   # 매번 확인!
FRONT_THRESHOLD = 0.55
BACK_THRESHOLD  = 0.4
```

### 2-6. 실행

```bash
python3 pcb_inspector.py
```

- 실행하면 기본 `FRONT CHECK` 모드로 시작
- 화면 하단 `FRONT CHECK` / `BACK CHECK` 버튼으로 모드 전환, 전환 후엔 매 프레임 판정
- `q`로 종료

---

## 3. code 폴더 (STM32F411RE 펌웨어) 빌드 및 플래시

`code/` = board_guard 저장소의 mcu_m4 브랜치 펌웨어 그대로. Windows + ARM GNU 툴체인 기준.

### 3-1. 툴체인 확인

`code/Makefile` 상단 `TOOL_DIR` 경로가 실제 설치 경로랑 맞는지 먼저 확인:

```makefile
TOOL_DIR = C:\arm-gnu-toolchain-15.2.rel1-mingw-w64-i686-arm-none-eabi
```

이 경로에 `arm-gnu-toolchain-15.2.rel1-mingw-w64-i686-arm-none-eabi`가 없으면, [ARM GNU Toolchain](https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads)에서 15.2.1 버전을 받아 그 경로에 설치하거나 Makefile의 `TOOL_DIR`을 실제 설치 경로로 수정.

### 3-2. 빌드 (make)

```bash
cd code
make
```

- `main.c`, `system_control.c`, `jetson.c`, `servo.c`, `step_motor.c`, `sensor_control.c`, `alarm.c`, `led.c` 등 `*.c` 전부 컴파일 → `rom_0x08000000.elf` → `rom_0x08000000.bin` 생성
- `__dump.txt`, `__dump_all.txt`에 디스어셈블리 덤프도 같이 생성됨 (디버깅용, 정상 동작이면 무시 OK)

빌드 정리하고 싶으면:
```bash
make clean
```

### 3-3. 보드에 플래시

STM32CubeProgrammer가 설치돼 있어야 함(CLI 포함). Makefile에 `run` 타겟이 이미 정의돼 있음:

```bash
make run
```

## 4. Jetson ↔ M4 연결 및 전체 기동

배선 (README 기준):

| Jetson GPIO | 신호 | M4(STM32) 핀 |
|---|---|---|
| STOP | PCB 진입 감지 → 정지 | PC10 (EXTI) |
| PASS | 양품 판정 | PC11 (EXTI) |
| FAIL | 불량 판정 | PC12 (EXTI) |

확인된 이슈: 모터/모터드라이버발 노이즈로 한 핀 신호가 인접 핀까지 같이 High로 잡히는 현상이 있었음 → **신호선에 10kΩ 저항**을 추가해서 해결한 상태. 배선 다시 잡을 때 이 저항 빠뜨리지 말 것.

### 기동 순서

1. 폰 IP Webcam 서버 ON (1번 세팅 완료 상태)
2. mcu 보드 전원 인가 (컨베이어 벨트 대기 상태로 자동 진입)
3. Jetson에서 `python3 pcb_inspector.py` 실행 → GPIO로 M4와 신호 주고받기 시작
4. PCB를 벨트에 투입하면:
   - 카메라가 배경 diff로 진입 감지 → Jetson이 STOP 신호 전송 → M4가 컨베이어 정지
   - PatchCore 판정(PASS/FAIL) → 불량이면 결함 위치·유형까지 산출
   - 판정 결과를 PASS/FAIL 신호로 M4에 전달
     - PASS → 컨베이어 재가동
     - FAIL → 스텝모터 이송 → 서보 push로 배출 → 컨베이어 재가동
5. 판정 결과는 Jetson 쪽 SQLite DB + 웹 대시보드(`web.py`, Flask)에서 실시간 확인 가능