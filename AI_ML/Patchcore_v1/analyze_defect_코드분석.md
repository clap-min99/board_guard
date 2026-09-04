# analyze_defect.py 코드 분석

## 전체 구조

크게 세 부분으로 나뉨: **① 위치 탐지 유틸 함수들 → ② 부품 영역 매칭 함수 → ③ 결함 위치 추출 →
④ 메인 분석 로직(`analyze`)**

---

## ① 위치 탐지 관련 함수

### `load_gray_ref(path, size)`
기준 이미지(빈 배경 사진)를 읽어서, 크기 통일(256x256) → 흑백 변환 → 블러 처리까지 미리
해두는 전처리 함수. 이후 비교 연산을 가볍고 노이즈에 덜 민감하게 만들기 위한 준비 단계.

### `check_presence(frame_bgr, empty_ref_gray)`
지금 사진이 빈 배경이랑 픽셀 단위로 얼마나 다른지 계산해서, "PCB가 실제로 놓여있나"를 판단.
`diff > 25`인 픽셀 비율이 2%(`PRESENCE_RATIO_THRESHOLD`) 넘으면 "있음"으로 판정.
경고용이지 분석을 막진 않음 (없어도 계속 진행).

### `detect_pcb_box(frame_bgr, empty_ref_gray)`
같은 원리(배경과의 차이)로, 이번엔 비율이 아니라 PCB 전체의 사각형 좌표를 찾음.
- 차이 나는 픽셀들을 마스크로 만들고
- `MORPH_CLOSE`(구멍 메우기) → `MORPH_OPEN`(작은 노이즈 제거)로 다듬고
- `findContours`로 윤곽 찾은 다음, 가장 큰 덩어리 하나를 PCB로 간주
- 256 크기 기준으로 계산한 좌표를 원본 이미지 크기에 맞게 다시 스케일링해서 반환

---

## ② 부품 영역 매칭 함수

### `load_regions(path)`
`calibrate_regions.py`가 만든 json(`{"name": ..., "relative_box": [x1,y1,x2,y2]}` 리스트)을
그대로 읽어옴.

### `relative_to_absolute(relative_box, pcb_box)`
저장된 상대좌표(0~1 비율)를, 지금 사진에서 찾은 `pcb_box` 크기에 맞춰 실제 픽셀 좌표로 환산.
PCB가 카메라 앞에서 위치가 조금 달라져도 대응 가능하게 하는 핵심 로직.

### `box_overlap_ratio(box_a, box_b)`
두 사각형의 교집합 넓이를, `box_a`(결함 박스) 넓이로 나눈 비율. "결함 박스가 이 부품 영역이랑
얼마나 겹치나"를 0~1 값으로 계산.

### `identify_defect_causes(defect_boxes, pcb_box, regions)`
결함 박스마다 모든 부품 영역을 순회하면서 겹침 비율이 15%(`MIN_REGION_OVERLAP`) 넘는 걸
다 찾아서 이름 리스트로 묶음. 하나도 안 걸리면 `UNKNOWN_AREA`.

---

## ③ 결함 위치 추출

### `preprocess(frame)`
원본 이미지를 모델 입력 형식(256x256, RGB, 0~1 정규화, `(1,3,256,256)` 텐서 shape)으로 변환.

### `get_defect_boxes(pred_mask, width, height)`
모델이 준 이상/정상 흑백 마스크를, 원본 크기로 확대 → 노이즈 제거(`MORPH_OPEN`) →
윤곽선 찾기 → 사각형들로 변환. 필터링 조건 4개:
- 너무 작은 영역(300px² 미만) 제외
- 이미지 폭의 80% 넘는 너비면 제외 (전체를 덮는 노이즈성 박스 배제 의도)
- 높이가 8px 미만이면 제외 (너무 얇은 라인 노이즈 배제)
- 가로세로 비율이 15배 넘으면 제외 (비정상적으로 길쭉한 형태 배제)

---

## ④ 메인 로직 `analyze()` — 실행 순서

1. `side`에 따라 엔진/regions/threshold 세 가지 선택
2. 이미지 읽기
3. 빈 배경 대비 존재 여부 확인 (경고만)
4. TensorRT 엔진 로드 + 추론 실행 → `pred_score`, `pred_label`, `anomaly_map`, `pred_mask` 획득
5. `score >= threshold`면 FAIL, 아니면 PASS(여기서 종료)
6. `pred_mask`(우선) 또는 `anomaly_map`(대안)에서 결함 박스들 추출
7. 결함 박스가 하나도 없으면 "전체적인 이상" 메시지 출력하고 종료
8. `object_box` 찾고, 부품 영역이랑 매칭해서 원인 리스트 생성
9. 콘솔에 좌표+원인 출력, 이미지에 박스+라벨 그려서 `--out` 경로에 저장

---

## 함수 요약표

| 함수 | 역할 |
|---|---|
| `load_gray_ref` | 빈 배경 기준 이미지 전처리 |
| `check_presence` | PCB 존재 여부 판단 (경고용) |
| `detect_pcb_box` | PCB 전체 윤곽 바운딩박스 검출 (object_box) |
| `load_regions` | 부품 영역 json 로드 |
| `relative_to_absolute` | 상대좌표 → 실제 픽셀 좌표 변환 |
| `box_overlap_ratio` | 두 박스 겹침 비율 계산 |
| `identify_defect_causes` | 결함 박스와 부품 영역 매칭 → 원인 이름 리스트 |
| `preprocess` | 모델 입력 형식으로 이미지 변환 |
| `get_defect_boxes` | 마스크에서 결함 위치 사각형들 추출 (노이즈 필터링 포함) |
| `analyze` | 전체 분석 흐름 실행 (메인 함수) |
