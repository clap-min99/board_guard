# ai추론쪽 camera_thread() 함수 안에서 get_detections(img)에서 나온걸
# moviing_to로 받아서 하나 추론할때마다 판정을 쌓아서 확인하기




import os
import time
import cv2
from threading import Thread, Condition, Lock
from collections import Counter


one_history = []
one_history_detail = []
one_history_obox = []
one_history_bbox = []
two_history = []
moviing_to = []
check_number = 0

loop_count = 1
_missing_check = 1          # 한 pcb에 한 판정만 하게 함 1일때 pcb 판독 가능

def saveing_picture():
    # 고장난 거 사진 찍어서 저장할 용도
    pass

# 최근 60장의 판정 결과 투표 매번 투표하고나면 투표지는 싹다 지운다
def state_vote(history):
    if len(history) < 60:
        return "INSPECTING"
    else:
        count = Counter(history)
        answer = count.most_common(1)[0][0]
        history.clear()
    return answer

def get_detections(): # 내가 호출 할 함수 임의로 만듬
    #answer = {"class", "detail", "bounding_box"}
    answer = (0, None, (10,10,5,5))
    # 0이 멀쩡한놈 1이 비정상인놈
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


_l_temp = ["MISSING", None, "MISSING", None, None, None, check_number]
def check_loop(): # 추론결과 판단 함수
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
            _l_class, _l_detail, _l_object_box, _l_bounding_box = get_detections() # 저거 받아다 써야됨

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
            if _l_class == None:
                _l_temp = ["MISSING", None, "MISSING", None, None, None, check_number]
                one_history.clear()
                one_history_detail.clear()
                one_history_bbox.clear()
                one_history_obox.clear()
                _missing_check = 1


            # 뭔가 넘어왔음.
            else :
                if _missing_check == 1: #
                    # 3개다 판단해서 가장 많이 되는걸로 뽑아다 주기
                    # 미싱은 앞에서 처리했으니 성공 실패 검사중만 체크하면 됨.
                    one_history.append(_l_class)
                    one_history_detail.append(_l_detail)
                    one_history_obox.append(_l_object_box)
                    one_history_bbox.append(_l_bounding_box)
                    

                    _l_state = state_vote(one_history)
                    _l_state_detail = state_vote(one_history_detail)
                    _l_object_box = state_vote(one_history_obox)
                    _l_bounding_box = state_vote(one_history_bbox)
                    

                    print(_l_state)
                    if _l_state == "normal": # 정상 검출 됬음.
                        check_number += 1
                        _l_temp = ["PASS", "NORMAL", "PASS", _l_detail, _l_object_box, _l_bounding_box, check_number]
                        _missing_check = 0
                    elif _l_state == "defect": # 비정상이래요.
                        check_number += 1
                        _l_temp = ["FAIL", "DEEFECT", "FAIL", _l_detail, _l_object_box, _l_bounding_box, check_number]
                        _missing_check = 0
                    elif _l_state == "INSPECTING": # 검사중 이래요
                        _l_temp = ["INSPECTING", None, "INSPECTING", _l_detail, _l_object_box, _l_bounding_box, check_number]

                else:
                    pass

                # 옛날 것
                # 버그 발생 할 수 있음 한번의 if문 안에서 여러번의 state_vote 호출            
                # if state_vote(one_history) == 0: #정상인 상황 가장 많은거 여기다 넣기.
                #     check_number += 1
                #     _l_temp = ["PASS", "NORMAL", "PASS", None, _l_boun`ding_box, check_number]

                # elif state_vote(one_history) == 1: #비정상인 상황
                #     check_number += 1
                #     _l_temp = ["FAIL", "DEEFECT", "FAIL", "FAIL", _l_bounding_box, check_number]

                # elif state_vote(one_history) == "INSPECTING":
                #     _l_temp = ["INSPECTING", None, "INSPECTING", None, _l_bounding_box, check_number]

                # else:
                #     _l_temp = ["MISSING", None, "MISSING", None, None, check_number]

            # 검사 상태 관리 및 결과 확정 / get_inspection_result(_l_temp) 호출하면 원하는 answer나오게하기
            print(get_inspection_result(_l_temp))

            loop_count += 1
            print(loop_count)

    finally:
        pass


#경기 시자아아아아아아아악! 하겠습니다!!
if __name__ == "__main__":

    try:
        check_loop()

    except KeyboardInterrupt:
        print("\\n end")