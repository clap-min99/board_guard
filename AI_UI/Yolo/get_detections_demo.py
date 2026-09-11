"""
get_detections() - 동료 요청 인터페이스

반환값: (class, detail, object_box, bounding_box)
    class        : "normal" 또는 "defect"
    detail       : 신뢰도(confidence), 0~1 사이 float
    object_box   : PCB 전체가 화면에서 차지하는 영역 (x1, y1, x2, y2)
    bounding_box : 불량으로 판단된 부위의 영역 (x1, y1, x2, y2) - 정상이면 None

⚠️ 정확도(빠른 판정)와 위치정보(Grad-CAM) 둘 다 필요해서
   내부적으로 두 모델을 씁니다:
   - CLS_ENGINE_PATH : 빠른 판정용 TensorRT 엔진 (.engine)
   - CLS_PT_PATH     : Grad-CAM 위치 계산용 원본 모델 (.pt)

   FAIL일 때만 Grad-CAM(느림)을 추가로 돌리므로,
   정상 판정일 때는 거의 즉시 결과가 나옵니다.

⚠️ 인터페이스 필드 해석에 대해 동료분과 꼭 맞춰봐야 합니다.
   (특히 detail/object_box/bounding_box 의미가 이 스크립트의 가정과
    다르면 코드 안의 해당 부분만 바꾸면 됩니다.)
"""

import cv2
import torch
import numpy as np
from ultralytics import YOLO

from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent

CLS_ENGINE_PATH = str(MODEL_DIR / "model_cls.engine")
CLS_PT_PATH = str(MODEL_DIR / "best.pt")

CLASS_NAMES = {0: "defect", 1: "normal"}

# 두 모델을 미리 로드해둠 (매번 로드하면 느려짐)
_fast_model = YOLO(CLS_ENGINE_PATH, task="classify")
_pt_model = YOLO(CLS_PT_PATH)
_pt_model.model.eval()


def find_object_box(img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    _, thresh = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )

    contours, _ = cv2.findContours(
        thresh,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    contour_area = cv2.contourArea(largest)
    frame_area = img_bgr.shape[0] * img_bgr.shape[1]

    # 화면 면적의 5%보다 작으면 PCB가 아닌 것으로 처리
    if contour_area < frame_area * 0.05:
        return None

    x, y, w, h = cv2.boundingRect(largest)

    # 너무 가늘거나 작은 윤곽 제거
    if w < 80 or h < 80:
        return None

    return int(x), int(y), int(x + w), int(y + h)

def _compute_gradcam_box(img_bgr, target_class):
    """Grad-CAM으로 불량 부위 박스를 계산 (defect일 때만 호출됨)"""
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(img_rgb, (224, 224))
    img_tensor = torch.from_numpy(resized).permute(2, 0, 1).float().unsqueeze(0) / 255.0
    img_tensor.requires_grad_(True)

    activations = {}
    gradients = {}
    target_layer = _pt_model.model.model[9]

    def forward_hook(module, inp, out):
        activations['value'] = out

    def backward_hook(module, grad_in, grad_out):
        gradients['value'] = grad_out[0]

    h1 = target_layer.register_forward_hook(forward_hook)
    h2 = target_layer.register_full_backward_hook(backward_hook)

    output = _pt_model.model(img_tensor)
    logits = output[0] if isinstance(output, tuple) else output

    _pt_model.model.zero_grad()
    score = logits[0, target_class]
    score.backward()

    grads = gradients['value'][0]
    acts = activations['value'][0]
    weights = grads.mean(dim=(1, 2))

    cam = torch.zeros(acts.shape[1:], dtype=torch.float32)
    for i, w in enumerate(weights):
        cam += w * acts[i].detach()
    cam = torch.relu(cam)
    cam = cam / (cam.max() + 1e-8)
    cam = cam.detach().numpy()

    h1.remove()
    h2.remove()

    h, w = img_bgr.shape[:2]
    cam_resized = cv2.resize(cam, (w, h))
    mask = (cam_resized > 0.5).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    # 여러 영역이 잡히면 합쳐서 하나의 큰 박스로 반환
    all_x1, all_y1, all_x2, all_y2 = w, h, 0, 0
    found = False
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw * bh < 100:
            continue
        found = True
        all_x1 = min(all_x1, x)
        all_y1 = min(all_y1, y)
        all_x2 = max(all_x2, x + bw)
        all_y2 = max(all_y2, y + bh)

    if not found:
        return None
    return (all_x1, all_y1, all_x2, all_y2)


def get_detections(img_bgr):
    if img_bgr is None or img_bgr.size == 0:
        return None, None, None, None

    # PCB 존재 여부를 먼저 검사
    object_box = find_object_box(img_bgr)

    if object_box is None:
        return None, None, None, None

    # PCB가 있을 때만 분류 모델 실행
    results = _fast_model(img_bgr, imgsz=224, verbose=False)
    class_id = int(results[0].probs.top1)
    confidence = float(results[0].probs.top1conf.item())
    cls = CLASS_NAMES[class_id]

    bounding_box = None
    if cls == "defect":
        bounding_box = _compute_gradcam_box(
            img_bgr,
            target_class=class_id,
        )

        if bounding_box is None:
            bounding_box = object_box

    return cls, confidence, object_box, bounding_box

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("사용법: python3 get_detections_demo.py <이미지 경로>")
        sys.exit(1)

    img = cv2.imread(sys.argv[1])
    result = get_detections(img)
    cls, detail, object_box, bounding_box = result

    print("class       :", cls)
    print("detail      :", detail)
    print("object_box  :", object_box)
    print("bounding_box:", bounding_box)
