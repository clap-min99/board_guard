import cv2
import os
import threading
import time
from flask import Flask, Response, render_template_string, jsonify

### 추가
from collections import Counter

# get_detections_demo.py를 같은 폴더에 두고 이렇게 import (파일명이 다르면 맞춰서 수정)
from get_detections_demo import get_detections

### 추가
one_history = []
one_history_detail = []
one_history_obox = []
one_history_bbox = []
two_history = []
moviing_to = []
check_number = 0
loop_count = 1
_missing_check = 1          # 한 pcb에 한 판정만 하게 함 1일때 pcb 판독 가능

app = Flask(__name__)

# 핸드폰 카메라
CAMERA_URL = "http://10.205.212.205:8080/video"   # ⚠️ 실제 폰 화면에 뜨는 주소로 교체

# 저장 폴더 (촬영 기능 - 추가 데이터 수집용)
capture_dir = "./pcb"
os.makedirs(capture_dir, exist_ok=True)

cap = cv2.VideoCapture(CAMERA_URL)

frame = None            # 원본 프레임 (저장용, 오버레이 없음)
display_frame = None    # 텍스트/박스 오버레이 그려진 프레임 (화면용)
latest_result = {"result": None, "confidence": None, "object_box": None, "bounding_box": None}
result_lock = threading.Lock()
cnt = 1


### 186까지 추가
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
    global _l_state_bbox
    global _missing_check
    global _l_object_box

    try:
            #_l_class, _l_detail, _l_object_box, _l_bounding_box = get_detections(img) # 저거 받아다 써야됨
            _l_class, _l_detail, _l_object_box, _l_bounding_box = moviing_to
            print(moviing_to)
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
                   # one_history_detail.append(_l_detail)
                    #one_history_obox.append(_l_object_box)
                    #one_history_bbox.append(_l_bounding_box)
                    

                    _l_state = state_vote(one_history)
                    #_l_state_detail = state_vote(one_history_detail)
                    #_l_object_box = state_vote(one_history_obox)
                    #_l_bounding_box = state_vote(one_history_bbox)
                    

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
            #print(get_inspection_result(_l_temp))

            loop_count += 1
            print(loop_count)

    finally:
        pass




# ⚠️ 모델 로딩(YOLO(...))은 get_detections_demo.py 안에서
#    모듈 import 시점에 이미 한 번만 처리됨 (여기서 또 로드할 필요 없음)
def draw_overlay(img, label, confidence, object_box, bounding_box):
    """추론 결과를 화면에 그려주는 함수"""
    is_defect = (label == "defect")
    text = f"{'DEFECT' if is_defect else 'NORMAL'}  conf={confidence:.3f}"
    color = (0, 0, 255) if is_defect else (0, 200, 0)

    cv2.rectangle(img, (0, 0), (img.shape[1], 40), (30, 30, 30), -1)
    cv2.putText(img, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2, cv2.LINE_AA)

    if object_box:
        cv2.rectangle(img, object_box[:2], object_box[2:], (255, 200, 0), 1)  # PCB 전체: 옅은 하늘색

    if is_defect and bounding_box:
        cv2.rectangle(img, bounding_box[:2], bounding_box[2:], (0, 0, 255), 2)  # 불량 부위: 빨간색 굵게

    return img


def camera_thread():
    global frame, display_frame, latest_result
    global moviing_to

    while True:
        ret, img = cap.read()

        if not ret:
            continue

        frame = img  # 원본은 그대로 보관 (저장용, 오버레이 없음)

        # ---- 핵심: 이 함수 하나로 정상/불량 판정 + 위치정보까지 전부 처리 ----
        # 정상이면 빠르게 끝나고, 불량이면 내부적으로 Grad-CAM까지 추가로 돎
        label, confidence, object_box, bounding_box = get_detections(img)

        moviing_to = [label, confidence, object_box, bounding_box]

        ## 판정 하는 함수 넣어놓음
        check_loop()

        overlay = draw_overlay(img.copy(), label, confidence, object_box, bounding_box)

        with result_lock:
            display_frame = overlay
            latest_result = {
                "result": "FAIL" if label == "defect" else "PASS",
                "confidence": round(confidence, 4),
                "object_box": object_box,
                "bounding_box": bounding_box,
            }


threading.Thread(
    target=camera_thread,
    daemon=True
).start()


def generate_frames():
    while True:
        with result_lock:
            img_to_send = display_frame

        if img_to_send is None:
            time.sleep(0.03)
            continue

        ret, buffer = cv2.imencode(".jpg", img_to_send)
        if not ret:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" +
            buffer.tobytes() +
            b"\r\n"
        )


@app.route("/")
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>PCB Inspection</title>
        <style>
            #status { font-size: 22px; font-weight: bold; margin-top: 10px; }
            .pass { color: green; }
            .fail { color: red; }
        </style>
    </head>
    <body>
        <h2>Phone Camera</h2>
        <img src="/video_feed" width="640">
        <div id="status">대기 중...</div>
        <br>
        <button onclick="saveImage()">사진 저장</button>
        <p id="result"></p>

        <script>
        function saveImage() {
            fetch('/save')
            .then(response => response.text())
            .then(data => {
                document.getElementById('result').innerText = data;
            });
        }

        async function updateStatus() {
            const res = await fetch('/status');
            const data = await res.json();
            const el = document.getElementById('status');
            if (data.result) {
                el.innerText = data.result + '  (conf: ' + data.confidence.toFixed(3) + ')';
                el.className = data.result === 'PASS' ? 'pass' : 'fail';
            }
        }
        setInterval(updateStatus, 500);
        </script>
    </body>
    </html>
    """)


@app.route("/video_feed")
def video_feed():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/status")
def status():
    with result_lock:
        return jsonify(latest_result)


@app.route("/save")
def save():
    global cnt

    if frame is None:
        return "카메라 프레임 없음"

    filename = f"{capture_dir}/img_{cnt:04d}.jpg"
    cv2.imwrite(filename, frame)   # 오버레이 없는 원본 저장
    cnt += 1

    print("저장:", filename)
    return f"저장 완료: {filename}"


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        threaded=True
    )