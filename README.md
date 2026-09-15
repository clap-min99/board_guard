
# 보드가드

> **PCB 불량품 확인형 시스템**  

컨베이어 벨트 위에 올라와 있는 PCB를 카메라로 양품/불량품으로 판독하여 불량품은 불량 결과를 확인하여 기록 후 제거

## 동작 영상

#### 앞면 검사
![front](./assets/front.gif)

#### 뒷면 검사
![back](./assets/back.gif)


## Code

| Branch | 설명 | 담당 |
| --- | --- | --- |
| front | [MIDDLE](https://github.com/clap-min99/board_guard/tree/front) | 이양배 |
| hm | [WEB](https://github.com/clap-min99/board_guard/tree/hm) | 곽혜민 |
| mcu_m4 | [MCU](https://github.com/clap-min99/board_guard/tree/mcu_m4) | 이양배 |
| patchcore | [AI](https://github.com/clap-min99/board_guard/tree/patchcore) | 박수민, 김태환 |
| yolo | [AI](https://github.com/clap-min99/board_guard/tree/yolo) | 박수민, 김태환 |


## Contributors

| 이름 | GitHub | 담당 |
| --- | --- | --- |
| 박수민 | [박수민_GITHUB](https://github.com/clap-min99) | 팀장, AI 모델링 |
| 김태환 | [김태환_GITHUB](https://github.com/Tae86) | 팀원, AI 파이프라인, 기구물 |
| 곽혜민 | [곽혜민_GITHUB](https://github.com/hyehye12) | 팀원, UI/UX, DB |
| 이양배 | [이양배_GITHUB](https://github.com/twotwoship) | 팀원, 판정 로직, mcu 제어 |

## 개발 목표

1. PCB 양품/불량품 판독
2. 불량 발생 시 불량 원인(유형) 판독
3. 판독 결과에 따른 컨베이어 자동 배출 제어

## 핵심 특징

| 특징 | 설명 |
| --- | --- |
| 비지도 이상탐지 | PatchCore 기반 — 정상 데이터만으로 학습, 불량 라벨링 없이 이상 여부 판정 |
| 존재 여부 사전 판별 | 빈 배경 기준 이미지와의 픽셀 diff로 PCB `MISSING` 여부를 AI 추론 전에 먼저 체크 |
| 프레임 지연 방지 | 카메라 읽기를 별도 스레드로 분리해 최신 프레임만 유지(`latest_frame`), 추론 속도와 무관하게 지연 누적 방지 |
| 불량 위치 시각화 | anomaly map → contour 분석으로 결함 부위 bounding box 표시 |
| 불량 유형 분류 | 결함 crop 이미지를 임베딩으로 변환해 레퍼런스와 1-NN 매칭 → 불량 원인(유형) 추정 |
| 앞/뒷면 개별 모델 운용 | Front/Back 각각 별도 PatchCore 모델 + threshold(0.55 / 0.4) 적용 |
| 병행 실험 트랙 | PatchCore 외 Classification 기반 검사(웹 대시보드) 별도 검증 |
| Jetson-MCU 이벤트 연동 | GPIO 3라인(STOP/PASS/FAIL)으로 Jetson 판정 결과를 MCU 상태머신에 전달 |
| 상태머신 기반 배출 제어 | 스텝모터 이송 + 연속회전 서보 push 시퀀스로 불량품 자동 배출 |


## 시스템 구성

```text
로컬 컴퓨터
       │
       │ Local Web / HTTP :5000
       ▼
┌────────────────────────────────────┐
│         JETSON ORIN NANO           │
│                                    │
│  Flask Web                         │
│  카메라 입력 → 양품/불량품 판정        │
│  (PatchCore)                       │
└────────────────┬───────────────────┘
                 │ GPIO (PC10=STOP, PC11=PASS, PC12=FAIL)
                 ▼
┌────────────────────────────────────┐
│      M4 NUCLEO-64 (STM32F411RE)    │
│                                    │
│  상태머신 기반 제어                   │
│  스텝모터, 서보, LED, 부저            │
└────────────────┬───────────────────┘
                 │
                 ▼
       불량품 배출 및 컨베이어 벨트 재가동
```

### 역할 분리

| 구분 | 담당 기능 |
| --- | --- |
| JETSON ORIN NANO | 관리자 Web, AI 판정(양품/불량 + 불량 유형), GPIO 신호 송신 |
| M4 NUCLEO-64 | GPIO 이벤트 수신, 상태머신 제어, 스텝모터/서보/LED/부저 |

## 동작 과정

0. 컨베이어 벨트(스텝모터) 동작 중
1. 카메라 화면에 PCB 등장 → 빈 배경과의 diff로 존재 감지
2. Jetson이 STOP 신호 송신 → M4가 컨베이어 정지, 검사 대기
3. PatchCore로 양품/불량품 판독 (불량이면 위치까지 산출)
4. 불량인 경우 결함 crop을 임베딩 매칭해 불량 원인(유형) 판독
5. 판정 결과를 PASS/FAIL 신호로 M4에 전달
   - PASS → 컨베이어 재가동
   - FAIL → 스텝모터로 불량품을 배출 위치까지 이송 → 서보 push로 배출 → 컨베이어 재가동

### Hardware

| 구분 | 구성 |
| --- | --- |
| Controller | JETSON ORIN NANO, M4 NUCLEAR64 |
| Stepper Motor | 28BYJ-48 ×1 |
| Motor Driver | ULN2003 ×1 |
| Servo Motor | MG90S ×1 |
| LED | x2 |
| BUZZER | ×1 |

### Software

| 영역 | 구성 |
| --- | --- |
| JETSON ORIN NANO OS | JetPack (Ubuntu 기반, 64-bit) |
| AI / 추론 | Python, PyTorch, anomalib(PatchCore), Ultralytics(YOLO), ONNX, TensorRT, OpenCV, pycuda |
| Web | Python, Flask 3.1.3 |
| M4 NUCLAER64 | Embedded C, Visual Studio |

## 주요 기능

### Local Web

- 카메라 실시간 영상 표시
- 양품(PASS) / 불량(FAIL) / 보드없음(MISSING) 실시간 판정 표시
- 불량 시 결함 위치 bounding box 및 불량 유형 표시
- 판정 결과 기록(DB 저장)

## 프로젝트 구조

```text
board_guard/
├── AI_ML/
│   └── Patchcore/              # PatchCore 학습 파이프라인
│       ├── capture_dataset.py          # 학습용 정상/불량 사진 촬영
│       ├── capture_empty_reference.py  # MISSING 판별용 빈 배경 기준 촬영
│       ├── patchcore_hs04_front.ipynb  # 앞면 학습 노트북 (Colab)
│       ├── patchcore_hs04_back.ipynb   # 뒷면 학습 노트북 (Colab)
│       ├── trt_module.py               # TensorRT 추론 래퍼
│       └── pcb_inspector.py            # 검사 앱 (개발/테스트용)
│
├── AI_UI/
│   ├── Patchcore/               # 실전 배포용 PatchCore 검사 앱
│   │   ├── pcb_inspector.py
│   │   ├── classify_by_embedding.py    # 불량 유형(원인) 분류
│   │   ├── embedding_utils.py
│   │   ├── database.py                 # 판정 결과 기록
│   │   └── drawing.py                  # 검사 영역/결과 시각화
|
│
├── code/                         # M4 NUCLEO-64 펌웨어 (STM32F411RE)
│   ├── main.c                          # 메인 루프 / 이벤트 디스패치
│   ├── system_control.c                # 상태머신 (RUN/INSPECT/REJECT)
│   ├── jetson.c                        # Jetson GPIO(EXTI) 연동
│   ├── servo.c / step_motor.c          # 서보/스텝모터 제어
│   ├── sensor_control.c                # 주변장치 초기화
│   └── alarm.c / led.c                 # 부저 / LED 제어
│
└── refer/                        # STM32F411RE 데이터시트, 레퍼런스 매뉴얼
```

## 실행 방법
 
전체 셋업(휴대폰 카메라 연결, onnx→engine 변환, MCU 빌드/플래시, Jetson↔M4 연결까지)은 [Porting_Manual.md](./Porting_Manual.md) 참고


## 구현 검증
 
최종 채택 모델: `model_03` (backbone: wide_resnet50_2)
 
| 모델 | 학습 데이터 | AUROC | F1 | Threshold |
| --- | --- | --- | --- | --- |
| model_03_front | 벨트 정상 479장 / 불량 50장 | 1.0 | 1.0 | 0.55 |
| model_03_back | 벨트 정상 489장 / 불량 63장 | 0.999 | 1.0 | 0.4 |
 
- 박스 기구물 검증 단계를 마치고 컨베이어 벨트 실환경에서 최종 검증 완료
- 다양한 결함 유형(SOLDER_DEFECT, SCRATCH, IC_DAMAGED, CRYSTAL_MISSING 등 총 12종)에 대해 위치·유형 판정이 안정적으로 동작함을 실제 검출 결과로 확인
- AUROC: 정상/불량 구분 성능 지표(1에 가까울수록 우수) · F1: 정밀도와 재현율의 조화 평균 · Threshold: PASS/FAIL 판별 기준 점수
## 트러블슈팅
 
### 1. 카메라 프레임 지연 (3초 이상 딜레이)
 
**문제**: engine 로드 후 화면을 켜면 3초 이상 지연이 발생.
 
**원인**: `cv2.VideoCapture`가 IP Webcam 스트림에서 프레임을 계속 받는 중에도, 메인 루프가 추론이 끝날 때까지 `cap.read()`를 호출하지 않아 내부 버퍼에 읽지 않은 프레임이 계속 쌓임. 결과적으로 매 추론마다 몇 초 전 프레임을 처리하게 되어 지연이 누적됨.
 
```python
# 기존 코드 — 추론이 끝나야 다음 프레임을 읽음
while True:
    ok, frame = cap.read()
    cls, detail, boxes = get_detections_front(frame)  # 추론이 여기서 시간 소모
```
 
**해결**: 프레임 수신을 별도 스레드로 분리해 항상 최신 프레임(`latest_frame`)만 유지하고, 메인 루프(추론)는 그 값을 그대로 가져다 씀. 추론이 아무리 오래 걸려도 지연이 누적되지 않음.
 
```python
latest_frame = None
frame_lock = threading.Lock()
 
def frame_reader(cap):
    global latest_frame
    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        with frame_lock:
            latest_frame = frame  # 항상 가장 최근 프레임으로 덮어씀
 
threading.Thread(target=frame_reader, args=(cap,), daemon=True).start()
 
while True:
    with frame_lock:
        frame = latest_frame
    cls, detail, boxes = get_detections_front(frame)
```
 
### 2. Jetson–M4 GPIO 노이즈 (인접 핀 오인식)
 
**문제**: Jetson이 PC11(PASS) 한 핀만 HIGH로 보냈는데, M4에서 인접 핀인 PC10(STOP)·PC12(FAIL)까지 함께 HIGH로 인식되어 3개 핀 모두 인터럽트가 발생.
 
**원인**: Jetson 단독으로 신호를 발생시켰을 때는 문제가 없었음 → M4에 연결된 스텝모터/서보모터 및 모터드라이버에서 발생한 노이즈가 신호선에 유입되는 것으로 확인.
 
**해결**: Jetson–M4 신호선 구간에 **10kΩ 저항**을 추가해 노이즈를 억제, 오인식 해결.
 
### 3. PCB 부분 인식 오판정
 
**문제**: 컨베이어로 PCB가 이송되는 도중, 카메라 중앙에 도달하기 전 일부만 진입한 상태에서도 PCB로 인식해 정지·FAIL 판정이 반복 발생.
 
**원인**: 배경과의 밝기 차이가 일정 기준을 넘는 픽셀 비율만으로 물체 존재를 판단하던 기존 로직의 한계 — PCB가 화면에 얼마나 들어와 있는지는 고려하지 않음.
 
**해결**: PCB 인식 박스의 **중심 좌표가 지정 구간에 도달했을 때만** 정지·판정하도록 구조 변경. PCB가 카메라에 완전히 들어왔을 때만 검사가 트리거됨.
 
### 4. 결함 위치 박스 흔들림 (flickering)
 
**문제**: 실시간 스트림에서 결함 bounding box의 위치·개수가 프레임마다 계속 바뀌어 결과가 불안정하게 보임.
 
**원인**: 매 프레임 독립적으로 threshold를 적용해 anomaly map으로부터 박스를 새로 계산하는 구조라, 미세한 score 변동에도 박스가 생겼다 사라졌다 함.
 
**해결**: 실시간 프레임 단위 판정 대신, **FAIL 판정이 확정된 순간의 단일 프레임을 캡처**해 그 프레임 기준으로 결함 위치를 고정 판별하도록 구조 변경.
 
### 5. GPIO 신호 중복 송신
 
**문제**: 판정 진행 중 및 완료 후에도 동일한 판정 신호가 여러 번 반복 송신되어 M4 쪽에서 중복 인터럽트 발생.
 
**원인**: Jetson 측 판정 결과 송신 로직이 여러 시점에서 같은 신호를 계속 재전송하는 구조였음.
 
**해결**: 판정 로직을 단계별로 분리해 신호가 **정확히 1회만 전송**되도록 수정.