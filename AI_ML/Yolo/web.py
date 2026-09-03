import cv2
import os
import sqlite3
import time
import threading
import traceback
from flask import Flask, Response, render_template_string, jsonify
from PCB_BG_full import inspect_frame, get_inspection_result
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
    "pcb_box": None,
    "anomaly_box": None,
    "check_number": 0,
    "pass_count": 0,
    "fail_count": 0,
    "fail_rate": 0.0,
    "inspection_enabled": True,
}


def get_camera_frame():
    with frame_lock:
        if frame is None:
            return None, None

        return frame.copy(), frame_id

def inspection_thread():
    """test.py의 최신 모델 결과를 웹 표시 데이터로 동기화한다."""
    global latest_result
    last_signature = None

    while True:
        fail_result = None
        inspection_enabled.wait()
        result = get_inspection_result()
        signature = (
            result.get("state"),
            result.get("check_number"),
            repr(result.get("pcb_box")),
            repr(result.get("anomaly_box")),
            result.get("details"),
        )

        if signature == last_signature:
            threading.Event().wait(0.05)
            continue

        with stats_lock:
            if not inspection_enabled.is_set():
                continue

            if result["state"] == "PASS":
                inspection_stats["pass_count"] += 1
            elif result["state"] == "FAIL":
                inspection_stats["fail_count"] += 1

            pass_count = inspection_stats["pass_count"]
            fail_count = inspection_stats["fail_count"]
            total_count = pass_count + fail_count
            fail_rate = fail_count / total_count * 100 if total_count else 0.0

            latest_result = {
                **result,
                "inspection_id": latest_result["inspection_id"] + 1,
                "check_number": total_count,
                "pass_count": pass_count,
                "fail_count": fail_count,
                "fail_rate": round(fail_rate, 1),
                "inspection_enabled": True,
            }
        #     if result["state"] == "FAIL":
        #         fail_result = dict(latest_result)
            last_signature = signature

        # if fail_result is not None:
        #     try:
        #         save_fail_inspection(
                #    fail_result,
                #    get_camera_frame()[0],
                #    MODEL_NAME,
                #    DEVICE_NAME,
                #    )
        #     except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        #         print(f"FAIL 검사 결과 저장 실패: {error}")

        threading.Event().wait(0.05)

threading.Thread(
    target=inspection_thread,
    daemon=True
).start()


def inspection_worker():
    last_frame_id = -1

    while True:
        inspection_enabled.wait()

        image, current_frame_id = get_camera_frame()

        if image is None:
            time.sleep(0.05)
            continue

        if current_frame_id == last_frame_id:
            time.sleep(0.005)
            continue

        try:
            inspect_frame(image, current_frame_id)

        except Exception as error:
            print(f"프레임 추론 실패: {error}")
            traceback.print_exc()

            # 연속 오류 시 CPU를 과도하게 사용하지 않도록 잠시 대기
            time.sleep(0.5)

        else:
            # 정상적으로 처리한 프레임만 완료 처리
            last_frame_id = current_frame_id

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


def draw_inspection_boxes(image, result):
    if result.get("state") in ("MISSING", "STOPPED"):
        return image

    pcb_box = result.get("pcb_box")
    if pcb_box is not None:
        draw_box(image, pcb_box, (255, 120, 0), "PCB", 2)

    anomaly_box = result.get("anomaly_box")

    # FAIL이면서 anomaly_box가 있을 때만 빨간 박스 표시
    if result.get("state") == "FAIL" and anomaly_box is not None:
        draw_box(image, anomaly_box, (0, 0, 255), "ANOMALY", 3)

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
                                <div><span>FPS</span><strong id="camera-fps">0.0</strong></div>
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
                            <h2>불량 유형별 비율</h2>
                            <canvas id="defectChart" class="chart-canvas"></canvas>
                            <div class="legend">
                                <span><i style="background:#00d967; margin:10px"></i>정상</span>
                                <span><i style="background:#5c20d7; margin:10px"></i>파손</span>
                                <span><i style="background:#e2c729; margin:10px"></i>오염</span>
                                <span><i style="background:#b830cf; margin:10px"></i>납땜</span>
                                <span><i style="background:#94a3b8; margin:10px"></i>기타</span>
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

                const defectData = defectChart.data.datasets[0].data;
                if (data.state === 'PASS') {
                    defectData[0] += 1;
                } else {
                    const defectIndex = {
                        '파손': 1,
                        '오염': 2,
                        '납땜 불량': 3,
                        '기타 이상': 4
                    }[data.details] ?? 4;
                    defectData[defectIndex] += 1;
                }
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
                    document.getElementById('total-count').textContent = data.check_number;
                    document.getElementById('pass-count').textContent = data.pass_count;
                    document.getElementById('fail-count').textContent = data.fail_count;
                    document.getElementById('fail-rate').textContent = `${data.fail_rate}%`;
                    document.getElementById('camera-fps').textContent = data.camera_fps.toFixed(1);
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
                    labels: ['정상', '파손', '오염', '납땜', '기타'],
                    datasets: [{
                        data: [0, 0, 0, 0, 0],
                        backgroundColor: ['#00d967', '#5c20d7', '#e2c729', '#b830cf', '#94a3b8'],
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
    with stats_lock:
        latest_result = {
            **latest_result,
            "state": "STOPPED",
            "result": None,
            "message": "자동검사가 중단되었습니다.",
            "pcb_box": None,
            "anomaly_box": None,
            "inspection_enabled": False,
        }
        return jsonify(dict(latest_result))


@app.route("/inspection/start", methods=["POST"])
def start_inspection():
    global latest_result

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


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        threaded=True
    )
