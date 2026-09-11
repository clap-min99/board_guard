"""
pcb_inspector_app.py

앞면/뒷면 두 개의 PatchCore(TensorRT) 엔진을 동시에 로드해두고,
화면 하단 버튼을 클릭하면 그 순간 프레임으로 검사를 실행하는 앱.

get_detections_front(frame) / get_detections_back(frame)
    -> (class, detail, bounding_box, causes)
    class: "MISSING" | "PASS" | "FAIL"
    causes: 불량 위치와 겹치는 부품 영역 이름 리스트 (calibrate_regions.py로 미리 정의)
            -> 화면에 DEFECT 박스 옆에 표시됨. check_loop/상태머신 로직에는 영향 없음.

실행:
    python3 pcb_inspector_app.py
    화면의 [앞면 검사] / [뒷면 검사] 버튼 클릭, q로 종료

사전 준비:
    calibrate_regions.py로 front_regions.json / back_regions.json을 미리 만들어둬야 함.
"""
import time

import cv2
import json
import os
import threading
import time
import uuid
import numpy as np



import Jetson.GPIO as GPIO



from trt_module import TRTInferenceEngine
from collections import Counter
from classify_by_embedding import load_reference, classify_defect_type
from drawing import draw_inspection_boxes

one_history = []
one_history_detail = []
one_history_obox = []
one_history_bbox = []
two_history = []
moviing_to = []
check_number = 0
loop_count = 1
# 컨베이어 제어 단계 (UI의 PASS/FAIL/MISSING 표시와 별개)
WAIT_ENTRY = "WAIT_ENTRY"
SETTLING = "SETTLING"
VOTING = "VOTING"
WAIT_EXIT = "WAIT_EXIT"
_inspection_phase = WAIT_ENTRY
_settle_until = 0.0
_missing_since = None
_position_empty_ref = None

# 현장 조정값: x=좌우 이동, y=상하 이동. 좌표는 영상 크기 대비 비율.
POSITION_AXIS = "x"
TARGET_CENTER_MIN = 0.20
TARGET_CENTER_MAX = 0.60
STOP_SETTLE_SECONDS = 0.30
EXIT_MISSING_SECONDS = 0.50
GPIO_PULSE_SECONDS = 0.010
_l_temp = ["MISSING", None, "MISSING", None, None, None, check_number]
_inspection_state_lock = threading.RLock()
_l_causes = []
_l_defect_types = []
INSPECTION_SESSION_ID = uuid.uuid4().hex



GPIO.setmode(GPIO.BOARD)
GPIO.setup(29, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(31, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(33, GPIO.OUT, initial=GPIO.LOW)



# ========================================================
# 사진 저장할 설정 추가
# ========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "inspection_images")

OUTPUT_DIR_FAIL = os.path.join(OUTPUT_DIR, "fail")
OUTPUT_DIR_PASS = os.path.join(OUTPUT_DIR, "pass")


def get_inspection_image_filename(check_number, state):
    """Return a filename that cannot collide after an application restart."""
    return f"inspection_{INSPECTION_SESSION_ID}_{check_number}_{state}.jpg"

# ============================================================
# 설정
# ============================================================

FRONT_ENGINE_PATH = "model_front_03.engine"
BACK_ENGINE_PATH = "model_back_03.engine"
EMPTY_REFERENCE_PATH = "empty_reference.jpg"

FRONT_REGIONS_PATH = "front_regions.json"
BACK_REGIONS_PATH = "back_regions.json"

REFERENCE_EMBEDDINGS_PATH = "reference_embeddings.pt"

IMG_SIZE = 256

CAMERA_URL = "http://10.212.29.23:8080/video"   # 오늘 IP Webcam 주소로 수정

FRONT_THRESHOLD = 0.55
BACK_THRESHOLD = 0.4

PRESENCE_PIXEL_DIFF_THRESHOLD = 25
PRESENCE_RATIO_THRESHOLD = 0.02

MIN_BOX_AREA = 300
MAX_BOX_WIDTH_RATIO = 0.8
MIN_BOX_HEIGHT = 8
MAX_ASPECT_RATIO = 15

MIN_REGION_OVERLAP = 0.15  # defect box가 부품 영역과 이 비율 이상 겹쳐야 그 부품 이름을 붙임

WINDOW_NAME = "PCB Inspector"

# 버튼 레이아웃 (프레임 하단에 그려짐)
BUTTON_HEIGHT = 60
BUTTON_MARGIN = 10

# ============================================================
# lol
# ============================================================
def state_vote(history):
    if len(history) < 60:
        return "INSPECTING"
    else:
        count = Counter(history)
        answer = count.most_common(1)[0][0]
        history.clear()
    return answer

def get_inspection_result(temp_list): #UI에서 호출 할 함수
    
    # answer = {
    #     "state": "PASS",
    #     "result": "NORMAL",
    #     "message": "PASS",
    #     "details": None,
    #     "bounding_box": [10, 10, 5, 5]
    # }
    state, result, message, details, obox, bbox, chk_num = temp_list
    
    answer = {
        "state": state,
        "result": result,
        "message": message,
        "details": details,
        "objecting_box": obox,
        "bounding_box": bbox,
        "check_number": chk_num
    }

    return answer

def _send_gpio_pulse(pin):
    GPIO.output(pin, GPIO.HIGH)
    try:
        time.sleep(GPIO_PULSE_SECONDS)
    finally:
        GPIO.output(pin, GPIO.LOW)


def _check_loop_unlocked(cls, detail, boxes, frame, causes=None, defect_types=None):
    """중앙 도착 -> STOP 1회 -> 안정화 -> 투표 -> 결과 1회 -> 이탈 대기."""
    global _inspection_phase, _settle_until, _missing_since
    global _l_temp, _l_causes, _l_defect_types, check_number

    now = time.monotonic()

    # 확정 후에는 위치/판정을 갱신하지 않고 실제 이탈만 확인한다.
    if _inspection_phase == WAIT_EXIT:
        if cls == "MISSING":
            if _missing_since is None:
                _missing_since = now
            elif now - _missing_since >= EXIT_MISSING_SECONDS:
                _inspection_phase = WAIT_ENTRY
                _missing_since = None
                one_history.clear()
                _l_causes = []
                _l_defect_types = []
                _l_temp = ["MISSING", None, "MISSING", None, None, None, check_number]
        else:
            _missing_since = None
    else:
        pcb_box = None
        if cls != "MISSING" and _position_empty_ref is not None:
            pcb_box = detect_pcb_box(frame, _position_empty_ref)

        if _inspection_phase == WAIT_ENTRY:
            _l_causes = []
            _l_defect_types = []
            _l_temp = ["MISSING", None, "PCB 진입 대기", None, pcb_box, None, check_number]
            if pcb_box is not None:
                x1, y1, x2, y2 = pcb_box
                height, width = frame.shape[:2]
                if POSITION_AXIS == "x":
                    center = (x1 + x2) / (2.0 * width)
                    fully_inside = x1 > 0 and x2 < width
                else:
                    center = (y1 + y2) / (2.0 * height)
                    fully_inside = y1 > 0 and y2 < height
                #if fully_inside and TARGET_CENTER_MIN <= center <= TARGET_CENTER_MAX:
                if TARGET_CENTER_MIN <= center <= TARGET_CENTER_MAX:    
                    _inspection_phase = SETTLING
                    one_history.clear()
                    _send_gpio_pulse(29)
                    _settle_until = time.monotonic() + STOP_SETTLE_SECONDS
                    _l_temp = ["INSPECTING", None, "정지 안정화", None, pcb_box, None, check_number]

        elif _inspection_phase == SETTLING:
            if now >= _settle_until:
                _inspection_phase = VOTING
                one_history.clear()

        elif _inspection_phase == VOTING:
            if cls == "MISSING":
                # 이미 벨트를 멈췄으므로 진입 대기로 돌아가거나 STOP을 재송신하지 않는다.
                one_history.clear()
                _l_temp = ["INSPECTING", None, "PCB 재검출 대기", None, None, None, check_number]
            elif cls in ("PASS", "FAIL"):
                one_history.append(cls)
                voted = state_vote(one_history)
                _l_causes = [list(names) for names in (causes or [])] if voted != "PASS" else []
                _l_defect_types = list(defect_types or []) if voted != "PASS" else []
                _l_temp = ["INSPECTING", None, "INSPECTING", detail, pcb_box, boxes, check_number]
                if voted in ("PASS", "FAIL"):
                    # 저장 중 예외가 발생하더라도 같은 PCB에 다시 송신하지 않는다.
                    _inspection_phase = WAIT_EXIT
                    _missing_since = None
                    check_number += 1
                    _l_temp = [voted, "NORMAL" if voted == "PASS" else "DEFECT",
                               voted, detail, pcb_box, boxes, check_number]
                    _send_gpio_pulse(33 if voted == "PASS" else 31)
                    directory = OUTPUT_DIR_PASS if voted == "PASS" else OUTPUT_DIR_FAIL
                    os.makedirs(directory, exist_ok=True)
                    output_path = os.path.join(directory, get_inspection_image_filename(check_number, voted))
                    saved_frame = frame
                    if voted == "FAIL":
                        saved_frame = frame.copy()
                        draw_inspection_boxes(saved_frame, {
                            "state": "FAIL", "objecting_box": pcb_box,
                            "bounding_box": boxes, "causes": _l_causes,
                            "defect_types": _l_defect_types,
                        })
                    cv2.imwrite(output_path, saved_frame)
                    print(get_inspection_result(_l_temp))

    result = get_inspection_result(_l_temp)
    result["causes"] = [list(names) for names in _l_causes]
    result["defect_types"] = list(_l_defect_types)
    return result


def check_loop(cls, detail, boxes, frame, causes=None, defect_types=None):
    """잠금을 획득한 상태에서 프레임 판정 결과를 투표 상태에 반영한다."""
    with _inspection_state_lock:
        return _check_loop_unlocked(cls, detail, boxes, frame, causes, defect_types)


def reset_inspection_state():
    """누적 통계는 유지하고 현재 PCB의 투표 및 확정 상태만 초기화한다."""
    global _inspection_phase, _settle_until, _missing_since, _l_temp
    global _l_class, _l_detail, _l_bounding_box, _l_object_box
    global _l_causes, _l_defect_types

    with _inspection_state_lock:
        one_history.clear()
        one_history_detail.clear()
        one_history_obox.clear()
        one_history_bbox.clear()
        two_history.clear()
        moviing_to.clear()

        _l_class = "MISSING"
        _l_detail = None
        _l_bounding_box = None
        _l_object_box = None
        _inspection_phase = WAIT_ENTRY
        _settle_until = 0.0
        _missing_since = None
        _l_causes = []
        _l_defect_types = []
        _l_temp = [
            "MISSING", None, "MISSING",
            None, None, None, check_number,
        ]

# ============================================================
# 카메라 프레임 리더 (별도 스레드)
# ============================================================
# 판정(get_detections)이 카메라 전송 속도보다 느리면, cap.read()가 큐에 쌓인
# 오래된 프레임부터 순서대로 꺼내게 되어 지연이 계속 누적됨(수 초~10초까지).
# 그래서 카메라 읽기를 별도 스레드로 분리해 항상 "최신 프레임"만 유지하고,
# 메인 루프는 처리 속도와 무관하게 그 최신 프레임만 참고하도록 함.

latest_frame = None
frame_lock = threading.Lock()


def frame_reader(cap: cv2.VideoCapture) -> None:
    global latest_frame
    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        with frame_lock:
            latest_frame = frame

# ============================================================
# 존재 여부 체크 / PCB 윤곽(object_box) 검출
# ============================================================

def load_empty_reference(path: str, size: int = 256) -> np.ndarray:
    global _position_empty_ref
    ref = cv2.imread(path)
    if ref is None:
        raise RuntimeError(
            f"기준 이미지를 못 찾음: {path}. capture_empty_reference.py로 먼저 찍어야 함."
        )
    ref = cv2.resize(ref, (size, size))
    ref_gray = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    _position_empty_ref = cv2.GaussianBlur(ref_gray, (5, 5), 0)
    return _position_empty_ref


def check_presence(frame_bgr: np.ndarray, empty_ref_gray: np.ndarray) -> tuple[bool, float]:
    size = empty_ref_gray.shape[0]
    frame_small = cv2.resize(frame_bgr, (size, size))
    frame_gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
    frame_gray = cv2.GaussianBlur(frame_gray, (5, 5), 0)

    diff = cv2.absdiff(frame_gray, empty_ref_gray)
    changed_pixels = int(np.sum(diff > PRESENCE_PIXEL_DIFF_THRESHOLD))
    ratio = changed_pixels / diff.size

    return ratio >= PRESENCE_RATIO_THRESHOLD, ratio


def detect_pcb_box(frame_bgr: np.ndarray, empty_ref_gray: np.ndarray):
    """빈 배경과의 차이로 PCB 전체 윤곽의 바운딩박스를 찾음 (object_box).
    반환: (x1, y1, x2, y2) 원본 프레임 좌표계, 못 찾으면 None"""
    size = empty_ref_gray.shape[0]
    h0, w0 = frame_bgr.shape[:2]
    frame_small = cv2.resize(frame_bgr, (size, size))
    frame_gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
    frame_gray = cv2.GaussianBlur(frame_gray, (5, 5), 0)

    diff = cv2.absdiff(frame_gray, empty_ref_gray)
    mask = (diff > PRESENCE_PIXEL_DIFF_THRESHOLD).astype(np.uint8) * 255

    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest)

    scale_x = w0 / size
    scale_y = h0 / size
    x1 = int(x * scale_x)
    y1 = int(y * scale_y)
    x2 = int((x + w) * scale_x)
    y2 = int((y + h) * scale_y)
    return (x1, y1, x2, y2)


# ============================================================
# 부품 영역(regions) 로드 / 좌표 변환 / 겹침 판정
# ============================================================

def load_regions(path: str) -> list[dict]:
    """calibrate_regions.py로 만든 json 로드. regions: [{"name": str, "relative_box": [x1,y1,x2,y2]}]"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["regions"]


def relative_to_absolute(relative_box, pcb_box):
    rx1, ry1, rx2, ry2 = relative_box
    px1, py1, px2, py2 = pcb_box
    pw, ph = px2 - px1, py2 - py1
    return (
        int(px1 + rx1 * pw),
        int(py1 + ry1 * ph),
        int(px1 + rx2 * pw),
        int(py1 + ry2 * ph),
    )


def box_overlap_ratio(box_a, box_b) -> float:
    """box_a 면적 대비, box_a와 box_b가 겹치는 비율."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    return inter / area_a if area_a > 0 else 0.0


def identify_defect_causes(defect_boxes, pcb_box, regions) -> list[list[str]]:
    """각 defect box마다, 겹치는 부품 영역 이름들을 찾음. pcb_box가 없으면 빈 리스트."""
    if pcb_box is None or not regions:
        return [[] for _ in defect_boxes]

    causes = []
    for dbox in defect_boxes:
        matched = []
        for r in regions:
            abs_box = relative_to_absolute(r["relative_box"], pcb_box)
            if box_overlap_ratio(dbox, abs_box) >= MIN_REGION_OVERLAP:
                matched.append(r["name"])
        causes.append(matched if matched else ["UNKNOWN_AREA"])
    return causes


# ============================================================
# 전처리 / 결함 위치 박스
# ============================================================

def preprocess(frame: np.ndarray) -> np.ndarray:
    image = cv2.resize(frame, (IMG_SIZE, IMG_SIZE))
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image = image.astype(np.float32) / 255.0
    image = np.transpose(image, (2, 0, 1))
    image = np.expand_dims(image, axis=0)
    return image.astype(np.float32)


def get_defect_boxes(pred_mask: np.ndarray, original_width: int, original_height: int):
    mask = np.squeeze(pred_mask)
    mask = (mask > 0).astype(np.uint8) * 255
    mask = cv2.resize(mask, (original_width, original_height), interpolation=cv2.INTER_NEAREST)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < MIN_BOX_AREA:
            continue
        if w > original_width * MAX_BOX_WIDTH_RATIO:
            continue
        if h < MIN_BOX_HEIGHT:
            continue
        aspect_ratio = max(w / max(h, 1), h / max(w, 1))
        if aspect_ratio > MAX_ASPECT_RATIO:
            continue
        boxes.append((x, y, x + w, y + h))

    return boxes


# ============================================================
# 핵심 판정 함수 - 팀 인터페이스
# ============================================================

def get_detections(frame_bgr, trt_engine, empty_ref_gray, threshold, regions,
                    embedding_model=None, reference=None):
    """반환: (class, detail, bounding_box, causes, defect_types)
    embedding_model/reference를 안 넘기면 defect_types는 항상 빈 리스트로 나옴
    (유형 분류 기능 없이 부위 분석만 쓰고 싶을 때 대비)."""
    is_present, diff_ratio = check_presence(frame_bgr, empty_ref_gray)
    if not is_present:
        return "MISSING", diff_ratio, [], [], []

    input_data = preprocess(frame_bgr)
    outputs = trt_engine.infer(input_data)

    score = float(np.squeeze(outputs["pred_score"]))
    is_fail = score >= threshold

    bounding_box = []
    causes = []
    defect_types = []
    if is_fail:
        if "pred_mask" in outputs:
            bounding_box = get_defect_boxes(outputs["pred_mask"], frame_bgr.shape[1], frame_bgr.shape[0])
        elif "anomaly_map" in outputs:
            anomaly_map = np.squeeze(outputs["anomaly_map"])
            pred_mask = (anomaly_map >= threshold).astype(np.uint8)
            bounding_box = get_defect_boxes(pred_mask, frame_bgr.shape[1], frame_bgr.shape[0])

        if bounding_box:
            pcb_box = detect_pcb_box(frame_bgr, empty_ref_gray)
            causes = identify_defect_causes(bounding_box, pcb_box, regions)

            # 결함 박스마다 그 부분만 잘라내서 유형 분류 (여러 개 나오면 각각 따로 판정)
            if embedding_model is not None and reference is not None:
                for (x1, y1, x2, y2) in bounding_box:
                    crop = frame_bgr[y1:y2, x1:x2]
                    if crop.size == 0:
                        defect_types.append(None)
                        continue
                    type_name, _distance = classify_defect_type(crop, reference, embedding_model)
                    defect_types.append(type_name)
            else:
                defect_types = [None] * len(bounding_box)

    cls = "FAIL" if is_fail else "PASS"
    return cls, score, bounding_box, causes, defect_types


# ============================================================
# 화면 그리기
# ============================================================

def draw_defect_box(frame, box, cause_names, type_name):
    x1, y1, x2, y2 = box
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)

    area_text = ", ".join(cause_names) if cause_names else "UNKNOWN_AREA"
    if type_name:
        label = f"{area_text} ({type_name})"
    else:
        label = f"{area_text} (미분류)"

    cv2.putText(
        frame, label, (x1, max(y1 - 8, 20)),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2, cv2.LINE_AA,
    )


def draw_result_banner(frame, side_label, cls, detail):
    color_map = {"MISSING": (0, 165, 255), "PASS": (0, 200, 0), "FAIL": (0, 0, 255)}
    color = color_map.get(cls, (200, 200, 200))
    text = f"[{side_label}] {cls}  detail={detail:.3f}"
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 40), (30, 30, 30), -1)
    cv2.putText(frame, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2, cv2.LINE_AA)


def draw_buttons(frame, active_mode):
    h, w = frame.shape[:2]
    btn_w = (w - BUTTON_MARGIN * 3) // 2

    front_rect = (BUTTON_MARGIN, h - BUTTON_HEIGHT - BUTTON_MARGIN,
                  BUTTON_MARGIN + btn_w, h - BUTTON_MARGIN)
    back_rect = (BUTTON_MARGIN * 2 + btn_w, h - BUTTON_HEIGHT - BUTTON_MARGIN,
                 BUTTON_MARGIN * 2 + btn_w * 2, h - BUTTON_MARGIN)

    buttons = [(front_rect, "FRONT CHECK", "front"), (back_rect, "BACK CHECK", "back")]
    for rect, label, mode_key in buttons:
        x1, y1, x2, y2 = rect
        color = (0, 140, 0) if active_mode == mode_key else (80, 80, 80)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, -1)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), 1)
        text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
        tx = x1 + (x2 - x1 - text_size[0]) // 2
        ty = y1 + (y2 - y1 + text_size[1]) // 2
        cv2.putText(frame, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

    return front_rect, back_rect


def point_in_rect(x, y, rect):
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2


# ============================================================
# 메인
# ============================================================

class AppState:
    def __init__(self):
        self.mode = None          # "front" | "back" | None (검사 안 하는 대기 상태)
        self.last_result = None   # (side_label, class, detail, boxes, causes, defect_types)


def make_mouse_callback(state: AppState, front_rect_holder, back_rect_holder):
    def on_mouse(event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        if point_in_rect(x, y, front_rect_holder[0]):
            state.mode = "front" if state.mode != "front" else None
        elif point_in_rect(x, y, back_rect_holder[0]):
            state.mode = "back" if state.mode != "back" else None

    return on_mouse


def main() -> None:
    #폴더 추가 ==============
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    os.makedirs(OUTPUT_DIR_FAIL, exist_ok=True)
    os.makedirs(OUTPUT_DIR_PASS, exist_ok=True)
    #=======================
    trt_front = TRTInferenceEngine(FRONT_ENGINE_PATH)
    trt_back = TRTInferenceEngine(BACK_ENGINE_PATH)
    empty_ref_gray = load_empty_reference(EMPTY_REFERENCE_PATH, size=IMG_SIZE)

    front_regions = load_regions(FRONT_REGIONS_PATH)
    back_regions = load_regions(BACK_REGIONS_PATH)

    # 불량 유형 분류용 - 프로그램 시작할 때 한 번만 로드 (매 프레임 로드하면 느려짐)
    reference, embedding_model = load_reference(REFERENCE_EMBEDDINGS_PATH)

    def get_detections_front(frame_bgr):
        return get_detections(frame_bgr, trt_front, empty_ref_gray, FRONT_THRESHOLD, front_regions,
                               embedding_model, reference)

    def get_detections_back(frame_bgr):
        return get_detections(frame_bgr, trt_back, empty_ref_gray, BACK_THRESHOLD, back_regions,
                               embedding_model, reference)

    cap = cv2.VideoCapture(CAMERA_URL)
    if not cap.isOpened():
        raise RuntimeError("카메라를 열 수 없습니다.")
    
    threading.Thread(target=frame_reader, args=(cap,), daemon=True).start()
    
    cv2.namedWindow(WINDOW_NAME)

    state = AppState()
    front_rect_holder = [(0, 0, 0, 0)]
    back_rect_holder = [(0, 0, 0, 0)]
    cv2.setMouseCallback(WINDOW_NAME, make_mouse_callback(state, front_rect_holder, back_rect_holder))

    print("FRONT/BACK 버튼을 클릭하면 그 모드로 전환되어 계속 판정됩니다. 같은 버튼 다시 클릭 시 대기 상태로 전환. q: 종료")

    try:
        while True:
            with frame_lock:
                frame = latest_frame

            if frame is None:
                time.sleep(0.01)
                continue
            frame = frame.copy()

            display = frame.copy()

            if state.mode == "front":
                cls, detail, boxes, causes, defect_types = get_detections_front(frame)
                state.last_result = ("FRONT", cls, detail, boxes, causes, defect_types)
                check_loop(cls, detail, boxes, frame, causes=causes, defect_types=defect_types)

            elif state.mode == "back":
                cls, detail, boxes, causes, defect_types = get_detections_back(frame)
                state.last_result = ("BACK", cls, detail, boxes, causes, defect_types)
                check_loop(cls, detail, boxes, frame, causes=causes, defect_types=defect_types)
                
            else:
                state.last_result = None

            if state.last_result is not None:
                side_label, cls, detail, boxes, causes, defect_types = state.last_result
                for box, cause_names, type_name in zip(boxes, causes, defect_types):
                    draw_defect_box(display, box, cause_names, type_name)
                draw_result_banner(display, side_label, cls, detail)
            else:
                cv2.rectangle(display, (0, 0), (display.shape[1], 40), (30, 30, 30), -1)
                cv2.putText(
                    display, "대기 중 - FRONT 또는 BACK 버튼을 눌러 검사 시작", (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA,
                )

            front_rect, back_rect = draw_buttons(display, state.mode)
            front_rect_holder[0] = front_rect
            back_rect_holder[0] = back_rect

            cv2.imshow(WINDOW_NAME, display)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
