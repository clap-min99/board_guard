# PCB 검사 시스템 - 코드 추가사항 정리 (1) 원리/개념

기존 `PCB_final_test` 프로젝트(PatchCore 단일 모델, front/back 이중 엔진 구조)에서
이번에 추가로 개발한 내용 중, **문제 원인과 해결 원리**를 정리한 문서.

---

## 1. 카메라 프레임 지연(최대 10초) 개선

**문제**: 실시간 화면과 실제 카메라 사이에 지연이 계속 누적되는 현상.

**원인**: 판정 처리(`get_detections`)가 카메라 전송 속도보다 느리면, `cap.read()`가
네트워크 버퍼에 쌓인 오래된 프레임부터 순서대로 꺼내게 되어 지연이 계속 쌓임.

**해결**: 카메라 읽기를 별도 스레드(`frame_reader`)로 분리해서 항상 "최신 프레임"만
`latest_frame` 변수에 덮어쓰기하고, 메인 루프는 처리 속도와 무관하게 그 최신 프레임만
참고하도록 변경.

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
            latest_frame = frame
```

메인 루프에서 `cap.read()` 대신 `latest_frame`을 참조하도록 변경.

**적용된 파일**: `pcb_inspector.py`, `pcb_inspector_ui.py`

---

## 2. 불량 원인(부품 위치) 분석 기능 추가

### 배경

기존에는 PatchCore가 "여기가 이상하다"는 위치(바운딩박스)까지만 알려줬음.
"어느 부품이 문제인지"(IC칩 근처, 핀 영역, 납땜 패드 등)까지 알려주는 기능을 추가.

### 원리

PatchCore 모델 자체는 부품의 의미(IC칩인지 핀인지)를 모름 — 그래서 모델에게 새로
학습시키는 대신, **좌표 기반 규칙**으로 해결:

1. 정상 PCB 사진에서 부품 영역(IC칩, 핀, 패드 등) 좌표를 **한 번만 수동으로 지정**
2. 이 좌표를 PCB 전체 박스(`object_box`) 기준 **상대 비율(0~1)**로 저장
   → 나중에 PCB 위치가 카메라 앞에서 살짝 움직여도, 매 프레임 다시 찾은 PCB 박스에
   맞춰 좌표를 재계산하므로 안정적으로 대응 가능
3. 판정 시 PatchCore가 뽑은 불량 위치(defect box)가 이 부품 영역들과 얼마나
   겹치는지 계산해서, 겹치는 영역 이름을 원인으로 출력

### 새로 추가된 함수

| 함수 | 역할 |
|---|---|
| `detect_pcb_box()` | 빈 배경(`empty_reference.jpg`)과의 차이로 PCB 전체 윤곽 바운딩박스를 찾음 (`object_box`, 기존에 미구현이었음) |
| `load_regions()` | `calibrate_regions.py`로 만든 부품 영역 json 로드 |
| `relative_to_absolute()` | 상대좌표(0~1)를 현재 프레임의 실제 픽셀 좌표로 변환 |
| `box_overlap_ratio()` | 두 사각형이 얼마나 겹치는지(교집합 면적 비율) 계산 |
| `identify_defect_causes()` | 결함 박스마다 겹치는 부품 영역 이름을 매칭 (15% 이상 겹쳐야 인정, 없으면 `UNKNOWN_AREA`) |
