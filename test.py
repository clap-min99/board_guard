import os
import time
import cv2
from threading import Thread, Condition, Lock
from collections import Counter


one_history = []
two_history = []
check_number = 0
result_lock = Lock()
latest_temp = ["INSPECTING", None, "INSPECTING", None, None, 0]

# 최근 60장의 판정 결과 투표 매번 투표하고나면 투표지는 싹다 지운다
def state_vote(one_history):
    if len(one_history) < 60:
        return "INSPECTING"
    else:
        count = Counter(one_history)
        answer = count.most_common(1)[0][0]
        one_history.clear()
    return answer

def normal_compare(): # 정상 조건 확인 함수
    return 0

def get_detections(frame=None): # 내가 호출 할 함수
    #answer = {"class", "detail", "bounding_box"}
    answer = ("0", None, [10,10,5,5])
    # 0이 멀쩡한놈 1이 비정상인놈
    return answer

def get_inspection_result(temp_list=None): #UI에서 호출 할 함수
    global latest_temp

    if temp_list is not None:
        with result_lock:
            latest_temp = list(temp_list)

    with result_lock:
        state, result, message, details, bbox, chk_num = latest_temp

    # answer = {
    #     "state": "PASS",
    #     "result": "NORMAL",
    #     "message": "PASS",
    #     "details": None,
    #     "bounding_box": [10, 10, 5, 5]
    # }
    answer = {
        "state": state,
        "result": result,
        "message": message,
        "details": details,
        "bounding_box": bbox,
        "check_number": chk_num
    }

    return answer

def check_loop(running_event=None, frame_provider=None): # 추론결과 판단 함수
    global _l_class
    global _l_detail
    global _l_bounding_box
    global _l_temp
    global check_number

    # 웹에서 프레임 공급자를 넘기면 UI와 동일한 IP 카메라 영상을 사용한다.
    # test.py를 단독 실행할 때만 로컬 카메라를 사용한다.
    _l_cap = None
    if frame_provider is None:
        _l_cap = cv2.VideoCapture(0)
        if not _l_cap.isOpened():
            raise RuntimeError("카메라 없따.")

    check_time = time.time()
    inspection_complete = False

    try:
        while _l_cap is None or _l_cap.isOpened():
            if running_event is not None:
                running_event.wait()

            # 여기서부터 시작임

            if frame_provider is not None:
                _l_frame = frame_provider()
            else:
                _l_ret, _l_frame = _l_cap.read()
                if not _l_ret:
                    time.sleep(0.01)
                    continue

            if _l_frame is None:
                time.sleep(0.01)
                continue

            # PCB 존재 판단
            _l_class, _l_detail, _l_bounding_box = get_detections(_l_frame)

            # 상태를 가지고 있어야함 PASS, FAIL, MISSING, INSPECTING

            # 여러 프레임 받아서 결과값 확정 처리하기 매 초마다 갱신하는거임.

            # 화면에 아무것도 안잡혀서 빈 리스트가 넘어올떄
            if _l_class == None:
                one_history.clear()
                inspection_complete = False
                _l_temp = ["MISSING", None, "MISSING", None, None, check_number]

            # 뭔가 넘어왔음.
            elif not inspection_complete:
                # 이게 클래스만 판단하는게 맞나? 클래스만판단해서 그 클래스랑 같이온 값넘겨저야됨
                #아래 넘겨줄때 손으로 직접작성해서 넘겨주면 안된다.
                one_history.append(_l_class)

                voted_state = state_vote(one_history)

                if voted_state in (0, "0"):
                    check_number += 1
                    _l_temp = ["PASS", "NORMAL", "PASS", None, _l_bounding_box, check_number]
                    inspection_complete = True

                elif voted_state in (1, "1"):
                    check_number += 1
                    _l_temp = ["FAIL", "DEFECT", "FAIL", _l_detail, _l_bounding_box, check_number]
                    inspection_complete = True

                elif voted_state == "INSPECTING":
                    _l_temp = ["INSPECTING", None, "INSPECTING", None, _l_bounding_box, check_number]

            # PASS/FAIL은 PCB가 MISSING이 될 때까지 _l_temp에 유지된다.
            get_inspection_result(_l_temp)

    finally:
        if _l_cap is not None:
            _l_cap.release()


#경기 시자아아아아아아아악! 하겠습니다!!
if __name__ == "__main__":

    try:
        check_loop()

    except KeyboardInterrupt:
        print("\\n end")
