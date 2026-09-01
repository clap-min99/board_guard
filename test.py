import os
import time
import cv2
from threading import Thread, Condition, Lock

def major_vote(): # 여러 프레임 결과 확정 함수

    return 0

def normal_compare(): # 정상 조건 확인 함수
    return 0

def get_detections(): # 호출 할 함수
    answer = {"class", "detail", "bounding_box"}

    return answer

def get_inspection_result(): #호출 시켜줄 함수
    
    answer = {"state","result","message","details","bounding_box"}
    answer = {"PASS","NORMAL","PASS","NULL",[10,10,5,5]}
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

