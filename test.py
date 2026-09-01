import os
import random
import time
import cv2
from threading import Thread, Condition, Lock

_mock_check_number = 0
_mock_lock = Lock()

def major_vote(): # 여러 프레임 결과 확정 함수

    return 0

def normal_compare(): # 정상 조건 확인 함수
    return 0

def get_detections(): # 호출 할 함수
    answer = {"class", "detail", "bounding_box"}

    return answer

def get_inspection_result(): #호출 시켜줄 함수
    """실제 모델 연결 전 화면 테스트용 랜덤 검사 결과."""
    global _mock_check_number

    time.sleep(0.7)
    state = random.choices(
        ["PASS", "FAIL", "MISSING"],
        weights=[60, 30, 10],
        k=1,
    )[0]

    with _mock_lock:
        if state in ("PASS", "FAIL"):
            _mock_check_number += 1
        check_number = _mock_check_number

    pcb_width = random.randint(320, 520)
    pcb_height = random.randint(220, 380)
    pcb_x = random.randint(0, 640 - pcb_width)
    pcb_y = random.randint(0, 480 - pcb_height)
    pcb_box = [pcb_x, pcb_y, pcb_width, pcb_height]

    if state == "PASS":
        return {
            "state": "PASS",
            "result": "NORMAL",
            "message": "PASS",
            "details": None,
            "pcb_box": pcb_box,
            "anomaly_box": None,
            "check_number": check_number,
        }

    if state == "FAIL":
        defect = random.choice(["파손", "오염", "납땜 불량", "기타 이상"])
        anomaly_width = random.randint(30, min(100, pcb_width))
        anomaly_height = random.randint(30, min(100, pcb_height))
        anomaly_x = random.randint(pcb_x, pcb_x + pcb_width - anomaly_width)
        anomaly_y = random.randint(pcb_y, pcb_y + pcb_height - anomaly_height)

        return {
            "state": "FAIL",
            "result": "DEFECT",
            "message": "FAIL",
            "details": defect,
            "pcb_box": pcb_box,
            "anomaly_box": [
                anomaly_x,
                anomaly_y,
                anomaly_width,
                anomaly_height,
            ],
            "check_number": check_number,
        }

    return {
        "state": "MISSING",
        "result": None,
        "message": "MISSING",
        "details": None,
        "pcb_box": None,
        "anomaly_box": None,
        "check_number": check_number,
    }

def check_loop(): # 추론결과 판단 함수
    global _l_class
    global _l_detail
    global _l_bounding_box

    _l_cap = cv2.VideoCapture(0)

    if not _l_cap.isOpened():
        raise RuntimeError("카메라 없따.")

    check_time = time.time()

    try:
        while _l_cap.isOpened():
            pass
    except Exception as e:
        raise RuntimeError(f"추론 처리 중 오류: {e}") from e
    finally:
        _l_cap.release()
