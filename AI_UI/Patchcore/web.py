import cv2
import os
import time
import threading
import traceback
import pycuda.driver as cuda
from flask import Flask, Response, render_template, jsonify, send_from_directory
from database import init_database, save_inspection, get_inspection_summary, get_recent_inspections
from history_api import history_api
from drawing import draw_inspection_boxes
from pcb_inspector_ui import (TRTInferenceEngine, load_empty_reference, get_detections, check_loop, reset_inspection_state, get_inspection_image_filename, FRONT_ENGINE_PATH,
BACK_ENGINE_PATH,EMPTY_REFERENCE_PATH,IMG_SIZE, FRONT_THRESHOLD,BACK_THRESHOLD,
OUTPUT_DIR_PASS, OUTPUT_DIR_FAIL, load_regions, FRONT_REGIONS_PATH,
BACK_REGIONS_PATH, REFERENCE_EMBEDDINGS_PATH,)
from classify_by_embedding import load_reference

# from database import init_database, save_fail_inspection

app = Flask(__name__)
app.register_blueprint(history_api)

# 핸드폰 카메라
CAMERA_URL = "http://172.30.6.127:8080/video"
CAMERA_RETRY_INTERVAL = 2
CAMERA_MAX_RETRIES = 3
CAMERA_STALE_SECONDS = 3
CAMERA_OFFLINE_SECONDS = 10
MODEL_NAME = "Patchcore"
DEVICE_NAME = "Jetson Orin Nano develop kit"
MODEL_VERSIONS = {
    "front": os.path.basename(FRONT_ENGINE_PATH),
    "back": os.path.basename(BACK_ENGINE_PATH),
}

init_database()
persisted_summary = get_inspection_summary()

cap = None

frame = None  # UI와 모델 추론이 함께 사용할 최신 프레임
camera_error = False
frame_id = 0
frame_lock = threading.Lock()
camera_fps = 0.0
camera_started_at = time.monotonic()
last_camera_frame_at = None
cnt = 1


def get_camera_status():
    """Report camera health even when OpenCV is blocked waiting for a frame."""
    with frame_lock:
        age = time.monotonic() - (
            last_camera_frame_at if last_camera_frame_at is not None else camera_started_at
        )
        if frame is not None and age < CAMERA_STALE_SECONDS:
            state = "live"
        elif camera_error or age >= CAMERA_OFFLINE_SECONDS:
            state = "offline"
        elif last_camera_frame_at is not None:
            state = "reconnecting"
        else:
            state = "connecting"
        return {
            "camera_state": state,
            "camera_fps": camera_fps if state == "live" else 0.0,
        }


def camera_thread():
    global cap, frame, camera_error, camera_fps, frame_id, last_camera_frame_at
    retry_count = 0
    fps_frame_count = 0
    fps_started_at = time.monotonic()

    while True:
        if cap is None or not cap.isOpened():
            if cap is not None:
                cap.release()
            cap = cv2.VideoCapture(CAMERA_URL)

            if not cap.isOpened():
                retry_count += 1
                with frame_lock:
                    camera_error = retry_count >= CAMERA_MAX_RETRIES
                    camera_fps = 0.0
                    frame = None
                time.sleep(CAMERA_RETRY_INTERVAL)
                continue

            fps_frame_count = 0
            fps_started_at = time.monotonic()

        ret, img = cap.read()

        if ret:
            received_at = time.monotonic()
            fps_frame_count += 1
            fps_elapsed = received_at - fps_started_at
            with frame_lock:
                frame = img
                frame_id += 1
                last_camera_frame_at = received_at
                camera_error = False
                if fps_elapsed >= 1.0:
                    camera_fps = round(fps_frame_count / fps_elapsed, 1)
            retry_count = 0
            if fps_elapsed >= 1.0:
                fps_frame_count = 0
                fps_started_at = received_at
            continue

        # 연결이 끊기면 현재 영상을 비우고 다음 반복에서 재연결한다.
        retry_count += 1
        with frame_lock:
            camera_error = retry_count >= CAMERA_MAX_RETRIES
            camera_fps = 0.0
            frame = None
        fps_frame_count = 0
        fps_started_at = time.monotonic()
        cap.release()
        time.sleep(CAMERA_RETRY_INTERVAL)


threading.Thread(
    target=camera_thread,
    daemon=True
).start()

inspection_stats = {
    "pass_count": persisted_summary["pass_count"],
    "fail_count": persisted_summary["fail_count"],
}

stats_lock = threading.Lock()
inspection_enabled = threading.Event()
inspection_enabled.set()
# test.py의 추론 결과와 UI 통계를 저장한다.
latest_result = {
    "inspection_id": persisted_summary["latest_id"],
    "state": "INSPECTING",
    "result": None,
    "message": "검사 시스템 준비 중",
    "details": None,
    "objecting_box": None,
    "bounding_box": None,
    "causes": [],
    "defect_types": [],
    "check_number": persisted_summary["total_count"],
    "pass_count": persisted_summary["pass_count"],
    "fail_count": persisted_summary["fail_count"],
    "fail_rate": persisted_summary["fail_rate"],
    "inspection_enabled": True,
    "active_side": "front",
}


def get_camera_frame():
    with frame_lock:
        if frame is None:
            return None, None

        return frame.copy(), frame_id


def get_saved_image_path(state, confirmed_number):
    """Return the current inspector's saved image path relative to this app."""
    directory = OUTPUT_DIR_PASS if state == "PASS" else OUTPUT_DIR_FAIL
    filename = get_inspection_image_filename(confirmed_number, state)
    image_path = os.path.join(directory, filename)
    if not os.path.isfile(image_path):
        return None

    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.relpath(image_path, base_dir)


def inspection_worker():
    """최신 카메라 프레임을 선택된 면의 PatchCore 모델로 검사한다."""
    global latest_result

    last_frame_id = -1
    last_side = None
    last_confirmed_check_number = 0
    cuda_context = None

    try:
        # CUDA 컨텍스트와 TensorRT 객체는 실제로 추론하는 이 스레드에서
        # 생성하고 계속 같은 스레드에서만 사용한다.
        cuda.init()
        cuda_context = cuda.Device(0).retain_primary_context()
        cuda_context.push()

        empty_ref_gray = load_empty_reference(
            EMPTY_REFERENCE_PATH,
            size=IMG_SIZE,
        )
        engines = {
            "front": TRTInferenceEngine(FRONT_ENGINE_PATH),
            "back": TRTInferenceEngine(BACK_ENGINE_PATH),
        }
        thresholds = {
            "front": FRONT_THRESHOLD,
            "back": BACK_THRESHOLD,
        }
        regions = {
            "front": load_regions(FRONT_REGIONS_PATH),
            "back": load_regions(BACK_REGIONS_PATH),
        }
        reference, embedding_model = load_reference(REFERENCE_EMBEDDINGS_PATH)

        while True:
            inspection_enabled.wait()

            image, current_frame_id = get_camera_frame()

            if image is None:
                time.sleep(0.05)
                continue

            if current_frame_id == last_frame_id:
                time.sleep(0.005)
                continue

            with stats_lock:
                active_side = latest_result.get("active_side", "front")

            try:
                # 앞/뒤 모델을 바꾸면 이전 모델의 투표 및 확정 상태를 버린다.
                if active_side != last_side:
                    reset_inspection_state()
                    last_side = active_side

                inference_started_at = time.perf_counter()
                cls, detail, boxes, causes, defect_types = get_detections(
                    image,
                    engines[active_side],
                    empty_ref_gray,
                    thresholds[active_side],
                    regions[active_side],
                    embedding_model=embedding_model,
                    reference=reference,
                )
                result = check_loop(
                    cls, detail, boxes, image,
                    causes=causes, defect_types=defect_types,
                )
                inference_ms = round(
                    (time.perf_counter() - inference_started_at) * 1000,
                    2,
                )

                # 중단 요청 또는 면 변경이 추론 도중 발생했다면 낡은 결과를 버린다.
                with stats_lock:
                    if (
                        not inspection_enabled.is_set()
                        or latest_result.get("active_side", "front") != active_side
                    ):
                        last_frame_id = current_frame_id
                        continue

                    confirmed_number = result.get("check_number", 0)
                    is_new_result = (
                        result.get("state") in ("PASS", "FAIL")
                        and confirmed_number > last_confirmed_check_number
                    )
                    if is_new_result:
                        inspection_id = save_inspection(
                            side=active_side,
                            state=result["state"],
                            score=result.get("details"),
                            threshold=thresholds[active_side],
                            image_path=get_saved_image_path(
                                result["state"],
                                confirmed_number,
                            ),
                            model_name=MODEL_NAME,
                            model_version=MODEL_VERSIONS[active_side],
                            inference_ms=inference_ms,
                            causes=result.get("causes", []),
                            defect_types=result.get("defect_types", []),
                        )
                        if result["state"] == "PASS":
                            inspection_stats["pass_count"] += 1
                        else:
                            inspection_stats["fail_count"] += 1
                        last_confirmed_check_number = confirmed_number

                    pass_count = inspection_stats["pass_count"]
                    fail_count = inspection_stats["fail_count"]
                    total_count = pass_count + fail_count
                    fail_rate = fail_count / total_count * 100 if total_count else 0.0

                    latest_result = {
                        **latest_result,
                        **result,
                        "inspection_id": (
                            inspection_id
                            if is_new_result
                            else latest_result["inspection_id"]
                        ),
                        "check_number": total_count,
                        "pass_count": pass_count,
                        "fail_count": fail_count,
                        "fail_rate": round(fail_rate, 1),
                        "inspection_enabled": True,
                        "active_side": active_side,
                    }

            except Exception as error:
                print(f"프레임 추론 실패: {error}")
                traceback.print_exc()
                time.sleep(0.5)

            else:
                last_frame_id = current_frame_id

    except Exception as error:
        print(f"검사 모델 초기화 실패: {error}")
        traceback.print_exc()
        with stats_lock:
            latest_result = {
                **latest_result,
                "state": "MODEL_ERROR",
                "result": None,
                "message": f"검사 모델 초기화 실패: {error}",
                "inspection_enabled": False,
            }
        inspection_enabled.clear()

    finally:
        if cuda_context is not None:
            cuda_context.pop()

threading.Thread(
    target=inspection_worker,
    daemon=True
).start()

def generate_frames():

    while True:

        if frame is None:
            time.sleep(0.05)
            continue

        display_frame = frame.copy()
        with stats_lock:
            display_result = dict(latest_result)

        # 최신 추론 박스를 영상 위에 그려서 UI로 전송한다.
        draw_inspection_boxes(display_frame, display_result)
        ret, buffer = cv2.imencode(".jpg", display_frame)

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
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():

    return Response(
        generate_frames(),
        mimetype=
        "multipart/x-mixed-replace; boundary=frame"
    )

@app.route("/inspection", methods=["GET"])
def inspection():
    with stats_lock:
        result = dict(latest_result)

    camera_status = get_camera_status()
    result.update(camera_status)
    result.update({
        "recent_inspections": get_recent_inspections(),
        "model_name": MODEL_NAME,
        "device_name": DEVICE_NAME,
        "threshold": BACK_THRESHOLD if result.get("active_side") == "back" else FRONT_THRESHOLD,
    })

    if camera_status["camera_state"] == "offline":
        result.update({
            "state": "CAMERA_ERROR",
            "result": None,
            "message": "카메라 연결에 실패했습니다.",
        })

    return jsonify(result)


@app.route("/inspection/images", methods=["GET"])
def inspection_images():
    images = []

    for state, directory in (("PASS", OUTPUT_DIR_PASS), ("FAIL", OUTPUT_DIR_FAIL)):
        if not os.path.isdir(directory):
            continue

        for filename in os.listdir(directory):
            if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
                continue

            file_path = os.path.join(directory, filename)
            try:
                saved_timestamp = os.path.getmtime(file_path)
            except OSError:
                continue

            images.append({
                "state": state,
                "filename": filename,
                "saved_at": time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(saved_timestamp),
                ),
                "saved_timestamp": saved_timestamp,
                "url": f"/inspection/images/{state.lower()}/{filename}",
            })

    images.sort(key=lambda item: item["saved_timestamp"], reverse=True)
    for item in images:
        item.pop("saved_timestamp")

    return jsonify(images[:20])


@app.route("/inspection/images/<state>/<path:filename>", methods=["GET"])
def inspection_image_file(state, filename):
    directory = {
        "pass": OUTPUT_DIR_PASS,
        "fail": OUTPUT_DIR_FAIL,
    }.get(state.lower())

    if directory is None:
        return jsonify({"message": "지원하지 않는 검사 상태입니다."}), 404

    return send_from_directory(directory, filename)


@app.route("/inspection/stop", methods=["POST"])
def stop_inspection():
    global latest_result

    inspection_enabled.clear()
    reset_inspection_state()
    with stats_lock:
        latest_result = {
            **latest_result,
            "state": "STOPPED",
            "result": None,
            "message": "자동검사가 중단되었습니다.",
            "objecting_box": None,
            "bounding_box": None,
            "causes": [],
            "defect_types": [],
            "inspection_enabled": False,
        }
        return jsonify(dict(latest_result))


@app.route("/inspection/start", methods=["POST"])
def start_inspection():
    global latest_result

    reset_inspection_state()
    with stats_lock:
        latest_result = {
            **latest_result,
            "state": "INSPECTING",
            "result": None,
            "message": "자동검사를 재개했습니다.",
            "causes": [],
            "defect_types": [],
            "inspection_enabled": True,
        }
    inspection_enabled.set()

    with stats_lock:
        return jsonify(dict(latest_result))


@app.route("/inspection/side/<side>", methods=["POST"])
def change_inspection_side(side):
    global latest_result

    if side not in ("front", "back"):
        return jsonify({"message": "검사 면은 front 또는 back이어야 합니다."}), 400

    reset_inspection_state()
    with stats_lock:
        latest_result = {
            **latest_result,
            "active_side": side,
            "state": "INSPECTING" if inspection_enabled.is_set() else "STOPPED",
            "message": f"{side.upper()} 검사로 변경했습니다.",
            "objecting_box": None,
            "bounding_box": None,
            "causes": [],
            "defect_types": [],
        }
        return jsonify(dict(latest_result))


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        threaded=True
    )
