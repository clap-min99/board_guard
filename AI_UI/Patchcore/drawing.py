"""검사 결과의 바운딩 박스를 이미지에 그리는 공용 함수."""

import cv2
import os
import warnings
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont


@lru_cache(maxsize=1)
def _label_font():
    paths = (
        os.environ.get("PCB_LABEL_FONT", ""),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    )
    for path in paths:
        if path and os.path.isfile(path):
            return ImageFont.truetype(path, 22)
    warnings.warn("한글 이미지 라벨용 폰트가 없습니다. PCB_LABEL_FONT에 한글 폰트 경로를 지정하세요.")
    return None


def _draw_label(image, label, x, y, color):
    """한글 라벨은 Pillow로 그려 OpenCV의 물음표 출력을 피한다."""
    font = _label_font() if not label.isascii() else None
    if font is not None:
        left, top, right, bottom = font.getbbox(label)
        width, height = right - left, bottom - top
        x = max(0, min(x, image.shape[1] - width - 8))
        y = max(0, min(y - height - 8, image.shape[0] - height - 8))
        roi = image[y:min(image.shape[0], y + height + 8), x:min(image.shape[1], x + width + 8)]
        canvas = Image.new("RGB", (roi.shape[1], roi.shape[0]), (20, 20, 20))
        ImageDraw.Draw(canvas).text((4 - left, 4 - top), label, font=font, fill=tuple(reversed(color)))
        roi[:] = np.asarray(canvas)[:, :, ::-1]
        return
    # 폰트가 없는 배포 환경에서도 박스와 영문 정보는 유지한다.
    label = label.encode("ascii", errors="replace").decode("ascii")
    (width, height), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    x = max(0, min(x, image.shape[1] - width - 8))
    y = max(height + 4, min(y - 8, image.shape[0] - baseline - 4))
    cv2.rectangle(image, (x, y - height - 4), (x + width + 8, y + baseline + 4), (20, 20, 20), -1)
    cv2.putText(image, label, (x + 4, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)


def draw_box(image, box, color, label, thickness):
    """[x1, y1, x2, y2] 좌표가 유효할 때만 박스를 그린다."""
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return

    try:
        x1, y1, x2, y2 = map(int, box)
    except (TypeError, ValueError):
        return

    frame_height, frame_width = image.shape[:2]
    x1 = max(0, min(x1, frame_width - 1))
    y1 = max(0, min(y1, frame_height - 1))
    x2 = max(0, min(x2, frame_width - 1))
    y2 = max(0, min(y2, frame_height - 1))

    if x2 <= x1 or y2 <= y1:
        return

    cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
    _draw_label(image, label, x1, y1, color)


def draw_boxes(image, boxes, color, label, thickness):
    """단일 박스와 여러 박스 목록을 모두 이미지에 그린다."""
    if not isinstance(boxes, (list, tuple)):
        return

    if len(boxes) == 4 and all(
        isinstance(value, (int, float)) for value in boxes
    ):
        draw_box(image, boxes, color, label, thickness)
        return

    for box_number, box in enumerate(boxes, start=1):
        draw_box(image, box, color, f"{label} {box_number}", thickness)


def draw_inspection_boxes(image, result):
    """검사 상태에 따라 PCB 및 불량 박스를 이미지에 그린다."""
    if result.get("state") in ("MISSING", "STOPPED"):
        return image

    objecting_box = result.get("objecting_box")
    if objecting_box is not None:
        draw_boxes(image, objecting_box, (255, 120, 0), "PCB", 2)

    bounding_box = result.get("bounding_box")
    if result.get("state") == "FAIL" and isinstance(bounding_box, (list, tuple)):
        if len(bounding_box) == 4 and all(isinstance(value, (int, float)) for value in bounding_box):
            bounding_box = [bounding_box]
        causes = result.get("causes") or []
        defect_types = result.get("defect_types") or []
        for index, box in enumerate(bounding_box):
            names = causes[index] if index < len(causes) else []
            area = ", ".join(names) if names else "UNKNOWN_AREA"
            defect_type = defect_types[index] if index < len(defect_types) else None
            label = f"{index + 1}: {area} / {defect_type or 'UNCLASSIFIED'}"
            draw_box(image, box, (0, 0, 255), label, 3)

    return image
