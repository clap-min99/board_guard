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
import numpy as np
import pycuda.autoinit  # noqa: F401

from trt_module import TRTInferenceEngine
from collections import Counter

one_history = []
one_history_detail = []
one_history_obox = []
one_history_bbox = []
two_history = []
moviing_to = []
check_number = 0
loop_count = 1
_missing_check = 1    
_l_temp = ["MISSING", None, "MISSING", None, None, None, check_number]

# ========================================================
# 사진 저장할 설정 추가
# ========================================================
OUTPUT_DIR = "./inspection_images"

# ============================================================
# 설정
# ============================================================

FRONT_ENGINE_PATH = "model_front.engine"
BACK_ENGINE_PATH = "model_back.engine"
EMPTY_REFERENCE_PATH = "empty_reference.jpg"

FRONT_REGIONS_PATH = "front_regions.json"
BACK_REGIONS_PATH = "back_regions.json"

IMG_SIZE = 256

CAMERA_URL = "http://10.116.224.98:8080/video"   # 오늘 IP Webcam 주소로 수정

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

def check_loop(cls, detail, boxes, frame): # 추론결과 판단 함수
    global loop_count

    global _l_class
    global _l_detail
    global _l_bounding_box
    global _l_temp
    global one_history
    global one_history_detail
    global one_history_obox
    global one_history_bbox
    global check_number
    global _l_state
    global _l_state_detail
    global _l_state_bbox
    global _missing_check
    global _l_object_box

    try:
            # 여기서부터 시작임 

            # PCB 존재 판단
            _l_class = cls
            _l_detail = detail
            _l_bounding_box = boxes
            _l_object_box = None
            #_l_class, _l_detail, _l_object_box, _l_bounding_box = get_detections() # 저거 받아다 써야됨

            # 상태를 가지고 있어야함 PASS, FAIL, MISSING, INSPECTING
            
            # 여러 프레임 받아서 결과값 확정 처리하기 60fps마다 갱신하는거임. 

            # 상태머신으로 만들기 위한 조건 
            # _l_state이 PASS와 FAIL 이되면 투표를 하면 안됨. 분기 조건을 정하자
            # _l_state이 INSPECTING 일때는 해도됨, MISSING 일 땐 해도 됨
            # 상태조건
            # MISSING -> INSPECTING -> PASS -> MISSING
            #                       -> FAIL ┘
            # 화면에 아무것도 안잡혀서 빈 리스트가 넘어올떄 미싱상태임. 
            # 지금 유사 상태머신임.
            if _l_class == "MISSING":
                _l_temp = ["MISSING", None, "MISSING", None, None, None, check_number]
                one_history.clear()
                #one_history_detail.clear()
                #one_history_bbox.clear()
                #one_history_obox.clear()
                _missing_check = 1


            # 뭔가 넘어왔음.
            else :
                if _missing_check == 1: #
                    # 3개다 판단해서 가장 많이 되는걸로 뽑아다 주기
                    # 미싱은 앞에서 처리했으니 성공 실패 검사중만 체크하면 됨.
                    one_history.append(_l_class)           

                    _l_state = state_vote(one_history)

                    print(_l_state)
                    if _l_state == "PASS": # 정상 검출 됬음.
                        check_number += 1

                        FILE_NAME = f"inspection_{check_number}_PASS.jpg"
                        OUTPUT_PATH = os.path.join(OUTPUT_DIR,FILE_NAME)
                        cv2.imwrite(OUTPUT_PATH, frame)

                        _l_temp = ["PASS", "NORMAL", "PASS", _l_detail, _l_object_box, _l_bounding_box, check_number]
                        _missing_check = 0
                        print(get_inspection_result(_l_temp))
                    elif _l_state == "FAIL": # 비정상이래요.
                        check_number += 1

                        FILE_NAME = f"inspection_{check_number}_FAIL.jpg"
                        OUTPUT_PATH = os.path.join(OUTPUT_DIR,FILE_NAME)
                        cv2.imwrite(OUTPUT_PATH, frame)
                        
                        _l_temp = ["FAIL", "DEFECT", "FAIL", _l_detail, _l_object_box, _l_bounding_box, check_number]
                        _missing_check = 0
                        print(get_inspection_result(_l_temp))
                    elif _l_state == "INSPECTING": # 검사중 이래요
                        _l_temp = ["INSPECTING", None, "INSPECTING", _l_detail, _l_object_box, _l_bounding_box, check_number]
                        print(get_inspection_result(_l_temp))
                else:
                    pass

            # 검사 상태 관리 및 결과 확정 / get_inspection_result(_l_temp) 호출하면 원하는 answer나오게하기
            

    finally:
        pass

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

def get_detections(frame_bgr, trt_engine, empty_ref_gray, threshold, regions):
    """반환: (class, detail, bounding_box, causes)"""
    is_present, diff_ratio = check_presence(frame_bgr, empty_ref_gray)
    if not is_present:
        return "MISSING", diff_ratio, [], []

    input_data = preprocess(frame_bgr)
    outputs = trt_engine.infer(input_data)

    score = float(np.squeeze(outputs["pred_score"]))
    is_fail = score >= threshold

    bounding_box = []
    causes = []
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

    cls = "FAIL" if is_fail else "PASS"
    return cls, score, bounding_box, causes


# ============================================================
# 화면 그리기
# ============================================================

def draw_defect_box(frame, box, cause_names):
    x1, y1, x2, y2 = box
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
    label = "DEFECT" if not cause_names else f"DEFECT: {', '.join(cause_names)}"
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
        self.last_result = None   # (side_label, class, detail, boxes, causes)


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
    #=======================
    trt_front = TRTInferenceEngine(FRONT_ENGINE_PATH)
    trt_back = TRTInferenceEngine(BACK_ENGINE_PATH)
    empty_ref_gray = load_empty_reference(EMPTY_REFERENCE_PATH, size=IMG_SIZE)

    front_regions = load_regions(FRONT_REGIONS_PATH)
    back_regions = load_regions(BACK_REGIONS_PATH)

    def get_detections_front(frame_bgr):
        return get_detections(frame_bgr, trt_front, empty_ref_gray, FRONT_THRESHOLD, front_regions)

    def get_detections_back(frame_bgr):
        return get_detections(frame_bgr, trt_back, empty_ref_gray, BACK_THRESHOLD, back_regions)

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
                cls, detail, boxes, causes = get_detections_front(frame)
                state.last_result = ("FRONT", cls, detail, boxes, causes)
                check_loop(cls, detail, boxes, frame)

            elif state.mode == "back":
                cls, detail, boxes, causes = get_detections_back(frame)
                state.last_result = ("BACK", cls, detail, boxes, causes)
                check_loop(cls, detail, boxes, frame)
                
            else:
                state.last_result = None

            if state.last_result is not None:
                side_label, cls, detail, boxes, causes = state.last_result
                for box, cause_names in zip(boxes, causes):
                    draw_defect_box(display, box, cause_names)
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