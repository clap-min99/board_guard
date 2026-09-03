import cv2
import os
import threading
import time
from flask import Flask, Response, render_template_string, jsonify

# get_detections_demo.py를 같은 폴더에 두고 이렇게 import (파일명이 다르면 맞춰서 수정)
from get_detections_demo import get_detections

app = Flask(__name__)

# 핸드폰 카메라
CAMERA_URL = "http://10.116.224.98:8080/video"   # ⚠️ 실제 폰 화면에 뜨는 주소로 교체

# 저장 폴더 (촬영 기능 - 추가 데이터 수집용)
capture_dir = "./pcb"
os.makedirs(capture_dir, exist_ok=True)

cap = cv2.VideoCapture(CAMERA_URL)

frame = None            # 원본 프레임 (저장용, 오버레이 없음)
display_frame = None    # 텍스트/박스 오버레이 그려진 프레임 (화면용)
latest_result = {"result": None, "confidence": None, "object_box": None, "bounding_box": None}
result_lock = threading.Lock()
cnt = 1

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

    while True:
        ret, img = cap.read()

        if not ret:
            continue

        frame = img  # 원본은 그대로 보관 (저장용, 오버레이 없음)

        # ---- 핵심: 이 함수 하나로 정상/불량 판정 + 위치정보까지 전부 처리 ----
        # 정상이면 빠르게 끝나고, 불량이면 내부적으로 Grad-CAM까지 추가로 돎
        label, confidence, object_box, bounding_box = get_detections(img)

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
