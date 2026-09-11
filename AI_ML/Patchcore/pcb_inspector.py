"""
pcb_inspector_app.py

앞면/뒷면 두 개의 PatchCore(TensorRT) 엔진을 동시에 로드해두고,
화면 하단 버튼을 클릭하면 그 순간 프레임으로 검사를 실행하는 앱.

get_detections_front(frame) / get_detections_back(frame)
    -> (class, detail, bounding_box)
    class: "MISSING" | "PASS" | "FAIL"

실행:
    python3 pcb_inspector_app.py
    화면의 [앞면 검사] / [뒷면 검사] 버튼 클릭, q로 종료
"""

import threading
import time

import cv2
import numpy as np
import pycuda.autoinit  # noqa: F401

from trt_module import TRTInferenceEngine

# ============================================================
# 설정
# ============================================================

FRONT_ENGINE_PATH = "model_front.engine"
BACK_ENGINE_PATH = "model_back.engine"
EMPTY_REFERENCE_PATH = "empty_reference.jpg"

IMG_SIZE = 256

CAMERA_URL = "http://192.168.21.50:8080/video"   # 오늘 IP Webcam 주소로 수정

FRONT_THRESHOLD = 0.55
BACK_THRESHOLD = 0.4

PRESENCE_PIXEL_DIFF_THRESHOLD = 25
PRESENCE_RATIO_THRESHOLD = 0.02

MIN_BOX_AREA = 300
MAX_BOX_WIDTH_RATIO = 0.8
MIN_BOX_HEIGHT = 8
MAX_ASPECT_RATIO = 15

WINDOW_NAME = "PCB Inspector"

# 버튼 레이아웃 (프레임 하단에 그려짐)
BUTTON_HEIGHT = 60
BUTTON_MARGIN = 10

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
# 존재 여부 체크
# ============================================================

def load_empty_reference(path: str, size: int = 256) -> np.ndarray:
    ref = cv2.imread(path)
    if ref is None:
        raise RuntimeError(
            f"기준 이미지를 못 찾음: {path}. capture_empty_reference.py로 먼저 찍어야 함."
        )
    ref = cv2.resize(ref, (size, size))
    ref_gray = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(ref_gray, (5, 5), 0)


def check_presence(frame_bgr: np.ndarray, empty_ref_gray: np.ndarray) -> tuple[bool, float]:
    size = empty_ref_gray.shape[0]
    frame_small = cv2.resize(frame_bgr, (size, size))
    frame_gray = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)
    frame_gray = cv2.GaussianBlur(frame_gray, (5, 5), 0)

    diff = cv2.absdiff(frame_gray, empty_ref_gray)
    changed_pixels = int(np.sum(diff > PRESENCE_PIXEL_DIFF_THRESHOLD))
    ratio = changed_pixels / diff.size

    return ratio >= PRESENCE_RATIO_THRESHOLD, ratio


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

def get_detections(frame_bgr, trt_engine, empty_ref_gray, threshold):
    """반환: (class, detail, bounding_box)"""
    is_present, diff_ratio = check_presence(frame_bgr, empty_ref_gray)
    if not is_present:
        return "MISSING", diff_ratio, []

    input_data = preprocess(frame_bgr)
    outputs = trt_engine.infer(input_data)

    score = float(np.squeeze(outputs["pred_score"]))
    is_fail = score >= threshold

    bounding_box = []
    if is_fail:
        if "pred_mask" in outputs:
            bounding_box = get_defect_boxes(outputs["pred_mask"], frame_bgr.shape[1], frame_bgr.shape[0])
        elif "anomaly_map" in outputs:
            anomaly_map = np.squeeze(outputs["anomaly_map"])
            pred_mask = (anomaly_map >= threshold).astype(np.uint8)
            bounding_box = get_defect_boxes(pred_mask, frame_bgr.shape[1], frame_bgr.shape[0])

    cls = "FAIL" if is_fail else "PASS"
    return cls, score, bounding_box


# ============================================================
# 화면 그리기
# ============================================================

def draw_defect_box(frame, box):
    x1, y1, x2, y2 = box
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
    cv2.putText(
        frame, "DEFECT", (x1, max(y1 - 8, 20)),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA,
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
        self.last_result = None   # (side_label, class, detail, boxes)


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
    trt_front = TRTInferenceEngine(FRONT_ENGINE_PATH)
    trt_back = TRTInferenceEngine(BACK_ENGINE_PATH)
    empty_ref_gray = load_empty_reference(EMPTY_REFERENCE_PATH, size=IMG_SIZE)

    def get_detections_front(frame_bgr):
        return get_detections(frame_bgr, trt_front, empty_ref_gray, FRONT_THRESHOLD)

    def get_detections_back(frame_bgr):
        return get_detections(frame_bgr, trt_back, empty_ref_gray, BACK_THRESHOLD)

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
                cls, detail, boxes = get_detections_front(frame)
                state.last_result = ("FRONT", cls, detail, boxes)
            elif state.mode == "back":
                cls, detail, boxes = get_detections_back(frame)
                state.last_result = ("BACK", cls, detail, boxes)
            else:
                state.last_result = None

            if state.last_result is not None:
                side_label, cls, detail, boxes = state.last_result
                for box in boxes:
                    draw_defect_box(display, box)
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