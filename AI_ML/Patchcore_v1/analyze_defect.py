"""
analyze_defect.py

이미 불량으로 확인된 PCB 사진 한 장을 입력받아,
어느 부품 영역(IC_CHIP, PIN_AREA, SOLDER_PAD 등)에서 이상이 감지됐는지 출력하는
사후 분석(post-hoc) CLI 스크립트.

실시간 카메라가 아니라 파일 하나를 분석하는 용도.

사전 준비:
    calibrate_regions.py로 front_regions.json / back_regions.json을 미리 만들어둬야 함.

실행:
    python3 analyze_defect.py --image defect_sample.jpg --side front
    python3 analyze_defect.py --image defect_sample.jpg --side back --out result.jpg
"""

import argparse
import json

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

FRONT_REGIONS_PATH = "front_regions.json"
BACK_REGIONS_PATH = "back_regions.json"

IMG_SIZE = 256

FRONT_THRESHOLD = 0.55  # pcb_inspector.py의 FRONT_THRESHOLD와 반드시 동일해야 함
BACK_THRESHOLD = 0.4    # pcb_inspector.py의 BACK_THRESHOLD와 반드시 동일해야 함

PRESENCE_PIXEL_DIFF_THRESHOLD = 25
PRESENCE_RATIO_THRESHOLD = 0.02

MIN_BOX_AREA = 300
MAX_BOX_WIDTH_RATIO = 0.8
MIN_BOX_HEIGHT = 8
MAX_ASPECT_RATIO = 15

MIN_REGION_OVERLAP = 0.15  # defect box가 부품 영역과 이 비율 이상 겹쳐야 그 부품 이름을 붙임


# ============================================================
# 존재 여부 체크 / PCB 윤곽(object_box) 검출
# ============================================================

def load_gray_ref(path: str, size: int = IMG_SIZE) -> np.ndarray:
    ref = cv2.imread(path)
    if ref is None:
        raise RuntimeError(f"기준 이미지를 못 찾음: {path}")
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
    반환: (x1, y1, x2, y2) 원본 이미지 좌표계, 못 찾으면 None"""
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
# 메인 분석 로직
# ============================================================

def analyze(image_path: str, side: str, out_path: str | None) -> None:
    if side == "front":
        engine_path = FRONT_ENGINE_PATH
        regions_path = FRONT_REGIONS_PATH
        threshold = FRONT_THRESHOLD
    else:
        engine_path = BACK_ENGINE_PATH
        regions_path = BACK_REGIONS_PATH
        threshold = BACK_THRESHOLD

    frame = cv2.imread(image_path)
    if frame is None:
        raise RuntimeError(f"이미지를 못 불러옴: {image_path}")

    empty_ref_gray = load_gray_ref(EMPTY_REFERENCE_PATH, size=IMG_SIZE)
    regions = load_regions(regions_path)

    is_present, presence_ratio = check_presence(frame, empty_ref_gray)
    if not is_present:
        print(f"[경고] PCB가 안 보이는 사진 같음 (presence_ratio={presence_ratio:.4f}). "
              f"그래도 분석은 계속 진행함.")

    trt_engine = TRTInferenceEngine(engine_path)
    input_data = preprocess(frame)
    outputs = trt_engine.infer(input_data)

    score = float(np.squeeze(outputs["pred_score"]))
    is_fail = score >= threshold

    print(f"\n=== 분석 결과: {image_path} ({side}) ===")
    print(f"anomaly score: {score:.4f}  (threshold={threshold})")
    print(f"판정: {'FAIL' if is_fail else 'PASS'}")

    if not is_fail:
        print("불량으로 판정되지 않아 원인 분석을 생략함.")
        return

    defect_boxes = []
    
    print(f"pred_mask 값 종류: {np.unique(outputs['pred_mask'])}")
    print(f"pred_mask 1(이상) 비율: {np.mean(outputs['pred_mask']):.4f}")
    amap = np.squeeze(outputs['anomaly_map'])
    print(f"anomaly_map min={amap.min():.4f}, max={amap.max():.4f}, mean={amap.mean():.4f}")

    if "pred_mask" in outputs:
        defect_boxes = get_defect_boxes(outputs["pred_mask"], frame.shape[1], frame.shape[0])
    elif "anomaly_map" in outputs:
        anomaly_map = np.squeeze(outputs["anomaly_map"])
        pred_mask = (anomaly_map >= threshold).astype(np.uint8)
        defect_boxes = get_defect_boxes(pred_mask, frame.shape[1], frame.shape[0])

    if not defect_boxes:
        print("불량 판정은 났지만, 위치 특정에 쓸 결함 영역을 못 찾음 (전체적인 이상일 수 있음).")
        return

    pcb_box = detect_pcb_box(frame, empty_ref_gray)
    if pcb_box is None:
        print("[경고] PCB 윤곽(object_box)을 못 찾아서 부품 영역 매칭을 할 수 없음.")
        causes = [[] for _ in defect_boxes]
    else:
        causes = identify_defect_causes(defect_boxes, pcb_box, regions)

    print(f"\n결함 위치 {len(defect_boxes)}곳 발견:")
    display = frame.copy()
    for i, (box, cause_names) in enumerate(zip(defect_boxes, causes), start=1):
        label = ", ".join(cause_names) if cause_names else "UNKNOWN"
        print(f"  [{i}] 좌표={box}  원인 추정: {label}")

        x1, y1, x2, y2 = box
        cv2.rectangle(display, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(display, label, (x1, max(y1 - 8, 20)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2, cv2.LINE_AA)

    if out_path:
        cv2.imwrite(out_path, display)
        print(f"\n결과 이미지 저장됨: {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="분석할 불량 사진 경로")
    parser.add_argument("--side", required=True, choices=["front", "back"], help="앞면/뒷면 선택")
    parser.add_argument("--out", default=None, help="결과(박스+원인 표시) 이미지 저장 경로 (선택)")
    args = parser.parse_args()

    analyze(args.image, args.side, args.out)


if __name__ == "__main__":
    main()
