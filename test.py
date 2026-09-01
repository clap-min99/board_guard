import os
import time
import cv2
from threading import Thread, Condition, Lock

# 마지막 1초의 판정 결과 저장
one_history = []
two_history = []

def normal_compare(): # 정상 조건 확인 함수
    return 0

def get_detections(): # 내가 호출 할 함수
    #answer = {"class", "detail", "bounding_box"}
    answer = ("0", None, [10,10,5,5])
    return answer

def get_inspection_result(): #UI에서 호출 할 함수
    
    answer = {
        "state": "PASS",
        "result": "NORMAL",
        "message": "PASS",
        "details": None,
        "bounding_box": [10, 10, 5, 5]
    }
    return answer

def check_loop(): # 추론결과 판단 함수
    global _l_class
    global _l_detail
    global _l_bounding_box

    _l_cap = cv2.VideoCapture(0)

    if not _l_cap.isOpened():
        raise RuntimeError("카메라 없따.")

    check_time = time.time()

    try:
        while _l_cap.isOpended():
            # 여기서부터 시작임 

            # PCB 존재 판단
            _l_class, _l_detail, _l_bounding_box = get_detections()

            # 상태를 가지고 있어야함 PASS, FAIL, MISSING, INSPECTING
            
            # 여러 프레임 받아서 결과값 확정 처리하기 매 초마다 갱신하는거임. 
            one_history.append(_l_class)

            # 정상 조건 비교 매 초마다 정상 조건인지 확인.
            normal_compare()

            # 검사 상태 관리 및 결과 확정 / get_inspection_result() 호출하면 원하는 answer나오게하기

    finally:
        _l_cap.release()


#경기 시자아아아아아아아악! 하겠습니다!!
if __name__ == "__main__":

    try:
        check_loop()

    except KeyboardInterrupt:
        print("\\n end")