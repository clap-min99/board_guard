"""검사 결과의 바운딩 박스를 이미지에 그리는 공용 함수."""

import cv2


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
    cv2.putText(
        image,
        label,
        (x1, max(24, y1 - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        color,
        2,
    )


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
    if result.get("state") == "FAIL" and bounding_box is not None:
        draw_boxes(image, bounding_box, (0, 0, 255), "ANOMALY", 3)

    return image
