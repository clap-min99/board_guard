import cv2
import os
import sqlite3
import time
import threading
import traceback
import pycuda.driver as cuda
from flask import Flask, Response, render_template_string, jsonify
from pcb_inspector import (TRTInferenceEngine, load_empty_reference, get_detections, check_loop, reset_inspection_state, FRONT_ENGINE_PATH,
BACK_ENGINE_PATH,EMPTY_REFERENCE_PATH,IMG_SIZE, FRONT_THRESHOLD,BACK_THRESHOLD,)

# from database import init_database, save_fail_inspection

app = Flask(__name__)

# 핸드폰 카메라
CAMERA_URL = "http://10.94.184.244:8080/video"
CAMERA_RETRY_INTERVAL = 2
CAMERA_MAX_RETRIES = 3
MODEL_NAME = "PCB-YOLOv11"
DEVICE_NAME = "Jetson Orin Nano develop kit"

# init_database()

cap = None

frame = None  # UI와 모델 추론이 함께 사용할 최신 프레임
camera_error = False
frame_id = 0
frame_lock = threading.Lock()
camera_fps = 0.0
cnt = 1


def camera_thread():
    global cap, frame, camera_error, camera_fps, frame_id
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
                camera_error = retry_count >= CAMERA_MAX_RETRIES
                camera_fps = 0.0
                frame = None
                time.sleep(CAMERA_RETRY_INTERVAL)
                continue

            fps_frame_count = 0
            fps_started_at = time.monotonic()

        ret, img = cap.read()

        if ret:
            with frame_lock:
                frame = img
                frame_id += 1
            retry_count = 0
            camera_error = False
            fps_frame_count += 1
            fps_elapsed = time.monotonic() - fps_started_at
            if fps_elapsed >= 1.0:
                camera_fps = round(fps_frame_count / fps_elapsed, 1)
                fps_frame_count = 0
                fps_started_at = time.monotonic()
            continue

        # 연결이 끊기면 현재 영상을 비우고 다음 반복에서 재연결한다.
        retry_count += 1
        camera_error = retry_count >= CAMERA_MAX_RETRIES
        camera_fps = 0.0
        fps_frame_count = 0
        fps_started_at = time.monotonic()
        frame = None
        cap.release()
        time.sleep(CAMERA_RETRY_INTERVAL)


threading.Thread(
    target=camera_thread,
    daemon=True
).start()

inspection_stats = {
    "pass_count": 0,
    "fail_count": 0
}

stats_lock = threading.Lock()
inspection_enabled = threading.Event()
inspection_enabled.set()
# test.py의 추론 결과와 UI 통계를 저장한다.
latest_result = {
    "inspection_id": 0,
    "state": "INSPECTING",
    "result": None,
    "message": "검사 시스템 준비 중",
    "details": None,
    "objecting_box": None,
    "bounding_box": None,
    "check_number": 0,
    "pass_count": 0,
    "fail_count": 0,
    "fail_rate": 0.0,
    "inspection_enabled": True,
    "active_side": "front",
}


def get_camera_frame():
    with frame_lock:
        if frame is None:
            return None, None

        return frame.copy(), frame_id


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
        cuda_context = cuda.Device(0).make_context()

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

                cls, detail, boxes = get_detections(
                    image,
                    engines[active_side],
                    empty_ref_gray,
                    thresholds[active_side],
                )
                result = check_loop(cls, detail, boxes, image)

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
                            latest_result["inspection_id"] + 1
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
    """단일 박스와 여러 박스 목록을 모두 영상에 그린다."""
    if not isinstance(boxes, (list, tuple)):
        return

    # [x1, y1, x2, y2] 형태의 단일 박스도 기존처럼 지원한다.
    if len(boxes) == 4 and all(
        isinstance(value, (int, float)) for value in boxes
    ):
        draw_box(image, boxes, color, label, thickness)
        return

    # [[x1, y1, x2, y2], ...] 형태의 모든 박스를 표시한다.
    for box_number, box in enumerate(boxes, start=1):
        draw_box(image, box, color, f"{label} {box_number}", thickness)


def draw_inspection_boxes(image, result):
    if result.get("state") in ("MISSING", "STOPPED"):
        return image

    objecting_box = result.get("objecting_box")
    if objecting_box is not None:
        draw_boxes(image, objecting_box, (255, 120, 0), "PCB", 2)

    bounding_box = result.get("bounding_box")

    # FAIL이면서 bounding_box 있을 때만 빨간 박스 표시
    if result.get("state") == "FAIL" and bounding_box is not None:
        draw_boxes(image, bounding_box, (0, 0, 255), "ANOMALY", 3)

    return image

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
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PCB 결함 모니터링 시스템</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
    </head>
    <body>
        <main class="dashboard">
            <header class="header">
                <h1>PCB 결함 모니터링 시스템</h1>
                <div class="inspection-control">
                    <button
                        id="inspection-toggle"
                        class="inspection-toggle"
                        onclick="toggleInspection()"
                    >
                        자동검사 중단
                    </button>
                </div>
            </header>
            <div class="content-grid">
                <section>
                    <div class="summary-grid">
                        <article class="summary-card">
                            <span>총 검사 수</span>
                            <strong id="total-count">0</strong>
                        </article>
                        <article class="summary-card">
                            <span>정상 수</span>
                            <strong id="pass-count">0</strong>
                        </article>
                        <article class="summary-card">
                            <span>불량 수</span>
                            <strong id="fail-count">0</strong>
                        </article>
                        <article class="summary-card">
                            <span>불량률</span>
                            <strong id="fail-rate">0.0%</strong>
                        </article>
                    </div>

                    <section class="camera-panel">
                        <div class="camera-screen">
                            <img src="/video_feed" alt="IP Webcam 영상">
                            <span class="live-badge"><i class="dot"></i>LIVE</span>
                            <div class="camera-info">
                                <button
                                    id="side-toggle"
                                    class="side-toggle"
                                    type="button"
                                    onclick="toggleSide()"
                                >FRONT</button>
                                <div><span>Model</span><strong id="model-name">-</strong></div>
                                <div><span>Device</span><strong id="device-name">-</strong></div>
                            </div>
                        </div>
                    </section>

                </section>

                <section>
                    <section class="result-panel">
                        <div class="result-value" id="result-value">
                            검사 시스템 준비 중
                        </div>
                    </section>

                    <div class="charts-top">
                        <article class="chart-card">
                            <h2>현재 PCB 이상 점수</h2>
                            <canvas id="defectChart" class="chart-canvas"></canvas>
                            <div class="legend">
                                <span><i style="background:#ef5964; margin:10px"></i>이상 점수</span>
                                <span><i style="background:#28a590; margin:10px"></i>정상 범위</span>
                            </div>
                        </article>

                        <article class="chart-card">
                            <h2>상태별 발생 건수</h2>
                            <canvas id="statusChart" class="chart-canvas"></canvas>
                        </article>
                    </div>

                    <article class="chart-card trend-card">
                        <h2>최근 검사 결과 (정상/불량)</h2>
                        <canvas id="trendChart" class="trend-canvas"></canvas>
                    </article>
                </section>
            </div>
        </main>

        <script>
            function displayInspectionResult(data) {
            const resultElement = document.getElementById('result-value');

            switch (data.state) {
                case 'PASS':
                    resultElement.textContent = `정상 · ${data.message}`;
                    resultElement.style.color = '#28a590';
                    break;

                case 'FAIL':
                    resultElement.textContent =
                        `불량 · ${data.details ?? data.message}`;
                    resultElement.style.color = '#ef5964';
                    break;

                case 'MISSING':
                    resultElement.textContent = 'PCB가 감지되지 않았습니다.';
                    resultElement.style.color = '#f59e0b';
                    break;

                case 'INSPECTING':
                    resultElement.textContent = '검사 중...';
                    resultElement.style.color = '#6175ff';
                    break;

                case 'STOPPED':
                    resultElement.textContent = '자동검사가 중단되었습니다.';
                    resultElement.style.color = '#ef5964';
                    break;

                case 'CAMERA_ERROR':
                    resultElement.textContent = '카메라 연결에 실패했습니다.';
                    resultElement.style.color = '#ef5964';
                    break;

                case 'MODEL_ERROR':
                    resultElement.textContent = data.message;
                    resultElement.style.color = '#ef5964';
                    break;

                default:
                    resultElement.textContent = '알 수 없는 검사 상태';
                    resultElement.style.color = '#64748b';
            }
            }

            function updateCharts(data) {
                const statusIndex = {
                    'PASS': 0,
                    'FAIL': 1,
                    'MISSING': 2
                }[data.state];

                if (statusIndex === undefined) {
                    return;
                }

                statusChart.data.datasets[0].data[statusIndex] += 1;
                statusChart.update();

                if (data.state === 'MISSING') {
                    return;
                }

                const detail = Number(data.details);
                const anomalyPercent = Number.isFinite(detail)
                    ? Math.max(0, Math.min(100, detail * 100))
                    : 0;
                defectChart.data.datasets[0].data = [
                    anomalyPercent,
                    100 - anomalyPercent
                ];
                defectChart.update();

                trendChart.data.labels.push(`${data.check_number}번`);
                trendChart.data.datasets[0].data.push(data.state === 'PASS' ? 1 : 0);
                if (trendChart.data.labels.length > 8) {
                    trendChart.data.labels.shift();
                    trendChart.data.datasets[0].data.shift();
                }
                trendChart.update();
            }

            let lastInspectionId = 0;
            let isPolling = false;
            let inspectionEnabled = true;
            let activeSide = 'front';

            function updateSideControl(data) {
                if (!data.active_side) return;

                activeSide = data.active_side;
                const button = document.getElementById('side-toggle');
                button.textContent = activeSide.toUpperCase();
                button.classList.toggle('is-back', activeSide === 'back');
            }

            async function toggleSide() {
                const button = document.getElementById('side-toggle');
                button.disabled = true;

                try {
                    const nextSide = activeSide === 'front' ? 'back' : 'front';
                    const response = await fetch(`/inspection/side/${nextSide}`, {
                        method: 'POST'
                    });
                    if (!response.ok) {
                        throw new Error(`검사 면 변경 실패: ${response.status}`);
                    }

                    updateSideControl(await response.json());
                } catch (error) {
                    console.error(error);
                    alert('검사 면을 변경하지 못했습니다.');
                } finally {
                    button.disabled = false;
                }
            }

            function updateInspectionControl(data) {
                const button = document.getElementById('inspection-toggle');
                inspectionEnabled = data.inspection_enabled;
                button.textContent = inspectionEnabled
                    ? '자동검사 중단'
                    : '자동검사 재개';
                button.classList.toggle('is-stopped', !inspectionEnabled);
            }

            async function toggleInspection() {
                const button = document.getElementById('inspection-toggle');
                button.disabled = true;

                try {
                    const endpoint = inspectionEnabled
                        ? '/inspection/stop'
                        : '/inspection/start';
                    const response = await fetch(endpoint, { method: 'POST' });
                    if (!response.ok) {
                        throw new Error(`검사 제어 실패: ${response.status}`);
                    }

                    const data = await response.json();
                    displayInspectionResult(data);
                    updateInspectionControl(data);
                } catch (error) {
                    console.error(error);
                    alert('자동검사 상태를 변경하지 못했습니다.');
                } finally {
                    button.disabled = false;
                }
            }

            async function fetchLatestInspection() {
                if (isPolling) return;
                isPolling = true;
                try {
                    const response = await fetch('/inspection');
                    if (!response.ok) {
                        throw new Error(`결과 조회 실패: ${response.status}`);
                    }

                    const data = await response.json();
                    displayInspectionResult(data);
                    updateInspectionControl(data);
                    updateSideControl(data);
                    document.getElementById('total-count').textContent = data.check_number;
                    document.getElementById('pass-count').textContent = data.pass_count;
                    document.getElementById('fail-count').textContent = data.fail_count;
                    document.getElementById('fail-rate').textContent = `${data.fail_rate}%`;
                    document.getElementById('model-name').textContent = data.model_name;
                    document.getElementById('device-name').textContent = data.device_name;

                    if (data.inspection_id > lastInspectionId && data.state !== 'INSPECTING') {
                        updateCharts(data);
                        lastInspectionId = data.inspection_id;
                        console.log('자동 검사 결과:', data);
                    }
                } catch (error) {
                    const resultElement = document.getElementById('result-value');
                    resultElement.textContent = '검사 결과를 불러오지 못했습니다.';
                    resultElement.style.color = '#ef5964';
                    console.error(error);
                } finally {
                    isPolling = false;
                }
            }

            fetchLatestInspection();
            setInterval(fetchLatestInspection, 500);

            const defectChart = new Chart(document.getElementById('defectChart'), {
                type: 'doughnut',
                data: {
                    labels: ['이상 점수', '정상 범위'],
                    datasets: [{
                        data: [0, 100],
                        backgroundColor: ['#ef5964', '#28a590'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '62%',
                    plugins: {
                        legend: { display: false },
                        tooltip: { enabled: true }
                    }
                }
            });

            const statusChart = new Chart(document.getElementById('statusChart'), {
                type: 'bar',
                data: {
                    labels: ['정상', '불량', '미감지'],
                    datasets: [{
                        data: [0, 0, 0],
                        backgroundColor: ['#28a590', '#ef5964', '#f59e0b'],
                        borderRadius: 4,
                        borderSkipped: false
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: '#28324a' },
                            ticks: {
                                precision: 0,
                                color: '#9ba8bc'
                            }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#9ba8bc' }
                        }
                    }
                }
            });

            const trendChart = new Chart(document.getElementById('trendChart'), {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        data: [],
                        borderColor: '#6175ff',
                        backgroundColor: 'rgba(97,117,255,0.18)',
                        fill: true,
                        tension: 0.35,
                        borderWidth: 3,
                        pointRadius: 5,
                        pointHoverRadius: 6,
                        pointBackgroundColor: '#6175ff',
                        pointBorderColor: '#ffffff',
                        pointBorderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            min: 0,
                            max: 1,
                            grid: { color: '#28324a' },
                            ticks: {
                                stepSize: 1,
                                color: '#9ba8bc',
                                callback: (value) => value === 1 ? '정상' : '불량'
                            }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#9ba8bc' }
                        }
                    }
                }
            });
        </script>
    </body>
    </html>
    """)


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

    result.update({
        "camera_fps": camera_fps,
        "model_name": MODEL_NAME,
        "device_name": DEVICE_NAME,
    })

    if camera_error:
        result.update({
            "state": "CAMERA_ERROR",
            "result": None,
            "message": "카메라 연결에 실패했습니다.",
        })

    return jsonify(result)


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
        }
        return jsonify(dict(latest_result))


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        threaded=True
    )
