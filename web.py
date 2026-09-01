import cv2
import os
import threading
from flask import Flask, Response, render_template_string, jsonify
from test import get_inspection_result

app = Flask(__name__)

# 핸드폰 카메라
CAMERA_URL = "http://10.94.184.244:8080/video"

cap = cv2.VideoCapture(CAMERA_URL)

frame = None
cnt = 1


def camera_thread():
    global frame

    while True:
        ret, img = cap.read()

        if ret:
            frame = img


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


def inspection_thread():
    """모델을 계속 실행하고 웹에서 조회할 최신 결과를 보관한다."""
    global latest_result

    while True:
        inspection_enabled.wait()

        with stats_lock:
            latest_result = {
                **latest_result,
                "state": "INSPECTING",
                "result": None,
                "message": "INSPECTING",
                "inspection_enabled": True,
            }

        result = get_inspection_result()

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

        # mock 결과를 화면에서 확인할 수 있도록 다음 검사 전 잠시 대기한다.
        threading.Event().wait(1.0)


threading.Thread(
    target=inspection_thread,
    daemon=True
).start()


def draw_box(image, box, color, label, thickness):
    """[x, y, width, height] 좌표가 유효할 때만 박스를 그린다."""
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return

    try:
        x, y, width, height = map(int, box)
    except (TypeError, ValueError):
        return

    if width <= 0 or height <= 0:
        return

    frame_height, frame_width = image.shape[:2]
    x1 = max(0, min(x, frame_width - 1))
    y1 = max(0, min(y, frame_height - 1))
    x2 = max(0, min(x + width, frame_width - 1))
    y2 = max(0, min(y + height, frame_height - 1))

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
    """PCB는 파란색, 이상 영역은 빨간색으로 표시한다."""
    if result.get("state") == "MISSING":
        return image

    pcb_box = (
        result.get("pcb_box")
        or result.get("bounding_box")
        or result.get("b_box")
    )
    draw_box(image, pcb_box, (255, 120, 0), "PCB", 2)

    anomaly_box = result.get("anomaly_box") or result.get("anomaly_boxes")
    if (
        isinstance(anomaly_box, (list, tuple))
        and len(anomaly_box) == 1
        and isinstance(anomaly_box[0], (list, tuple))
    ):
        anomaly_box = anomaly_box[0]

    draw_box(image, anomaly_box, (0, 0, 255), "ANOMALY", 3)
    return image

def generate_frames():

    while True:

        if frame is None:
            continue

        display_frame = frame.copy()
        with stats_lock:
            display_result = dict(latest_result)

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
        return jsonify(dict(latest_result))


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
