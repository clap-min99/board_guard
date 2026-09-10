const imageModal = document.getElementById('image-modal');
const modalPreview = document.getElementById('image-modal-preview');
const modalError = document.getElementById('image-modal-error');
let inspectionImages = [];
let currentModalImageIndex = -1;

function fitImageModal() {
    if (!imageModal.open || !modalPreview.naturalWidth || modalPreview.hidden) return;
    const maxWidth = document.documentElement.clientWidth * 0.96;
    const maxHeight = window.innerHeight * 0.96;
    const style = getComputedStyle(imageModal);
    const horizontalPadding = parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
    const verticalPadding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    imageModal.style.width = `${maxWidth}px`;
    // 폭이 줄어 헤더가 줄바꿈되는 경우에도 이미지 전체가 화면에 들어오게 한다.
    for (let i = 0; i < 3; i++) {
        const headerHeight = imageModal.querySelector('.image-modal-header').getBoundingClientRect().height;
        const scale = Math.min(
            Math.max(1, maxWidth - horizontalPadding) / modalPreview.naturalWidth,
            Math.max(1, maxHeight - verticalPadding - headerHeight) / modalPreview.naturalHeight
        );
        imageModal.style.width = `${modalPreview.naturalWidth * scale + horizontalPadding}px`;
    }
}

modalPreview.addEventListener('load', fitImageModal);
window.addEventListener('resize', fitImageModal);

function openInspectionImage(index) {
    if (index < 0 || index >= inspectionImages.length) return;

    currentModalImageIndex = index;
    const item = inspectionImages[index];
    const state = document.getElementById('image-modal-state');
    state.textContent = item.state;
    state.className = `result-badge-modal ${item.state.toLowerCase()}`;
    document.getElementById('image-modal-time').textContent = item.saved_at;
    modalError.hidden = true;
    modalPreview.hidden = false;
    modalPreview.alt = `${item.state} 검사 이미지 · ${item.saved_at}`;
    modalPreview.src = item.url;
    if (!imageModal.open) {
        imageModal.showModal();
        document.body.classList.add('image-modal-open');
    }
    if (modalPreview.complete) fitImageModal();
}

document.addEventListener('keydown', (event) => {
    if (!imageModal.open || event.altKey || event.ctrlKey || event.metaKey) return;

    if (event.key === 'ArrowLeft') {
        event.preventDefault();
        openInspectionImage(currentModalImageIndex - 1);
    } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        openInspectionImage(currentModalImageIndex + 1);
    }
});

modalPreview.addEventListener('error', () => {
    modalPreview.hidden = true;
    modalError.hidden = false;
});
document.getElementById('image-modal-close').addEventListener('click', () => imageModal.close());
imageModal.addEventListener('click', (event) => {
    const bounds = imageModal.getBoundingClientRect();
    if (event.target === imageModal && (
        event.clientX < bounds.left || event.clientX > bounds.right ||
        event.clientY < bounds.top || event.clientY > bounds.bottom
    )) imageModal.close();
});
imageModal.addEventListener('close', () => {
    document.body.classList.remove('image-modal-open');
    currentModalImageIndex = -1;
});

const historyModal = document.getElementById('history-modal');
const historyStateBadge = document.getElementById('history-state-badge');
const historyBody = document.getElementById('history-body');
const historySheet = document.getElementById('history-sheet');
const historySheetTitle = document.getElementById('history-sheet-title');
const historySheetCount = document.getElementById('history-sheet-count');
const historySheetRange = document.getElementById('history-sheet-range');
const historyPrev = document.getElementById('history-prev');
const historyNext = document.getElementById('history-next');
const historyPageLabel = document.getElementById('history-page');
const historyLoadStatus = document.getElementById('history-load-status');
const historyLoadMessage = document.getElementById('history-load-message');
const historyRetry = document.getElementById('history-retry');
const historyIndexes = [...document.querySelectorAll('[data-history-filter]')];
let activeHistoryState = 'PASS';
let activeHistoryFilter = null;
let historyPage = 1;
let historyRequest = null;

const historyFilterLabels = {
    all: '전체 기록',
    front: 'FRONT 검사',
    back: 'BACK 검사',
    latest: '최근 5건'
};

function appendHistoryCell(rowElement, value, className = '') {
    const cell = document.createElement('td');
    cell.textContent = value;
    if (className) cell.className = className;
    rowElement.appendChild(cell);
    return cell;
}

function formatHistoryNumber(value, digits) {
    return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';
}

function defectEntries(data) {
    const causes = Array.isArray(data.causes) ? data.causes : [];
    const types = Array.isArray(data.defect_types) ? data.defect_types : [];
    const boxes = Array.isArray(data.bounding_box) ? data.bounding_box : [];
    const boxCount = boxes.length === 4 && boxes.every(value => typeof value === 'number') ? 1 : boxes.length;
    return Array.from({ length: Math.max(causes.length, types.length, boxCount) }, (_, i) => ({
        number: i + 1,
        area: Array.isArray(causes[i]) && causes[i].length ? causes[i].join(', ') : '위치 미확인',
        type: types[i] || '미분류'
    }));
}

function renderHistoryRows(data) {
    historyBody.replaceChildren();
    for (const item of data.rows) {
        const row = document.createElement('tr');
        appendHistoryCell(row, String(item.id).padStart(4, '0'), 'spreadsheet-index');
        const date = new Date(item.inspected_at);
        appendHistoryCell(row, Number.isNaN(date.getTime()) ? item.inspected_at : date.toLocaleString('ko-KR', { hour12: false }));
        appendHistoryCell(row, item.side.toUpperCase(), `spreadsheet-side ${item.side}`);
        appendHistoryCell(row, item.state, `spreadsheet-result ${item.state.toLowerCase()}`);
        const defects = item.state === 'FAIL' ? defectEntries(item) : [];
        appendHistoryCell(row, defects.map(d => `${d.number}. ${d.area}`).join('\n') || '—', 'defect-cell');
        appendHistoryCell(row, defects.map(d => `${d.number}. ${d.type}`).join('\n') || '—', 'defect-cell');
        appendHistoryCell(row, formatHistoryNumber(item.score, 3), 'spreadsheet-number');
        appendHistoryCell(row, formatHistoryNumber(item.threshold, 2), 'spreadsheet-number');
        appendHistoryCell(row, `${formatHistoryNumber(item.inference_ms, 1)} ms`, 'spreadsheet-number');
        appendHistoryCell(row, item.model_version || item.model_name);
        historyBody.appendChild(row);
    }
    if (!data.rows.length) {
        const row = document.createElement('tr');
        appendHistoryCell(row, '저장된 검사 이력이 없습니다.', 'empty-row').colSpan = 10;
        historyBody.appendChild(row);
    }
    const start = (data.page - 1) * data.page_size;
    historySheetCount.textContent = `${data.total} ROWS`;
    historySheetRange.textContent = data.total ? `${start + 1}–${start + data.rows.length} / ${data.total}` : '0 / 0';
    historyPage = data.page;
    historyPageLabel.textContent = data.page;
    historyPrev.disabled = data.page <= 1;
    historyNext.disabled = data.page >= data.pages;
}

async function loadHistory(filter = null, page = 1) {
    historyRequest?.abort();
    const controller = new AbortController();
    historyRequest = controller;
    activeHistoryFilter = filter;
    historyPage = page;
    historySheet.hidden = filter === null;
    historyModal.classList.toggle('is-index-only', filter === null);
    historyLoadStatus.hidden = false;
    historyLoadMessage.textContent = '검사 이력을 불러오는 중입니다.';
    historyRetry.hidden = true;
    historyPrev.disabled = true;
    historyNext.disabled = true;
    historyBody.replaceChildren();
    historySheetCount.textContent = '—';
    historySheetRange.textContent = '—';
    historyPageLabel.textContent = page;
    if (filter) historySheetTitle.textContent = historyFilterLabels[filter];
    for (const index of historyIndexes) {
        const isActive = index.dataset.historyFilter === filter;
        index.classList.toggle('is-active', isActive);
        index.setAttribute('aria-selected', String(isActive));
    }
    historySheet.setAttribute('aria-busy', 'true');
    try {
        const params = new URLSearchParams({ state: activeHistoryState, filter: filter || 'all', page });
        const response = await fetch(`/inspection/history?${params}`, { signal: controller.signal, cache: 'no-store' });
        if (!response.ok) throw new Error(`검사 이력 조회 실패: ${response.status}`);
        const data = await response.json();
        if (controller.signal.aborted || historyRequest !== controller || !historyModal.open) return;
        for (const [key, count] of Object.entries(data.counts)) {
            document.querySelector(`[data-history-count="${key}"]`).textContent = String(count).padStart(3, '0');
        }
        if (filter) renderHistoryRows(data);
        historyLoadStatus.hidden = true;
    } catch (error) {
        if (controller.signal.aborted || historyRequest !== controller) return;
        historyLoadMessage.textContent = '검사 이력을 불러오지 못했습니다.';
        historyRetry.hidden = false;
        console.error(error);
    } finally {
        if (historyRequest === controller) historySheet.setAttribute('aria-busy', 'false');
    }
}

function openHistoryModal(state) {
    activeHistoryState = state;
    historyStateBadge.textContent = state;
    historyStateBadge.className = `history-state-badge ${state.toLowerCase()}`;
    document.getElementById('history-modal-title').textContent = state;
    document.getElementById('archive-drawer-label').textContent = `${state} FILES`;
    for (const count of document.querySelectorAll('[data-history-count]')) count.textContent = '—';
    if (!historyModal.open) historyModal.showModal();
    document.body.classList.add('history-modal-open');
    loadHistory();
}

for (const index of historyIndexes) {
    index.addEventListener('click', () => loadHistory(index.dataset.historyFilter));
}
historyPrev.addEventListener('click', () => loadHistory(activeHistoryFilter, historyPage - 1));
historyNext.addEventListener('click', () => loadHistory(activeHistoryFilter, historyPage + 1));
historyRetry.addEventListener('click', () => loadHistory(activeHistoryFilter, historyPage));

document.getElementById('history-modal-close').addEventListener('click', () => historyModal.close());
historyModal.addEventListener('click', (event) => {
    const bounds = historyModal.getBoundingClientRect();
    if (event.target === historyModal && (
        event.clientX < bounds.left || event.clientX > bounds.right ||
        event.clientY < bounds.top || event.clientY > bounds.bottom
    )) historyModal.close();
});
historyModal.addEventListener('close', () => {
    historyRequest?.abort();
    document.body.classList.remove('history-modal-open');
});

function displayInspectionResult(data) {
const resultElement = document.getElementById('result-value');
const detailElement = document.getElementById('defect-details');
detailElement.hidden = data.state !== 'FAIL';
detailElement.textContent = data.state === 'FAIL'
    ? defectEntries(data).map(d => `불량 위치 ${d.number} · 부품: ${d.area} / 유형: ${d.type}`).join('\n') || '부품·불량 유형 정보가 없습니다.'
    : '';

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

function updateAnomalyChart(data) {
    const detail = data.details == null || data.details === '' ? NaN : Number(data.details);
    const threshold = data.threshold == null || data.threshold === '' ? NaN : Number(data.threshold);
    document.getElementById('anomaly-score-value').textContent = Number.isFinite(detail)
        ? detail.toFixed(3) : '—';
    document.getElementById('normal-threshold-value').textContent = Number.isFinite(threshold)
        ? `< ${threshold.toFixed(2)}` : '—';
    const anomalyPercent = Number.isFinite(detail)
        ? Math.max(0, Math.min(100, detail * 100))
        : 0;
    defectChart.data.datasets[0].data = [
        anomalyPercent,
        100 - anomalyPercent
    ];
    defectChart.update();
}

let recentInspectionSignature = null;

function updateRecentInspectionChart(rows) {
    // The API returns newest first; the graph runs from oldest to newest.
    const recent = rows.slice(0, 10).reverse();
    const range = document.getElementById('recent-inspection-range');
    const formatTime = (value) => new Date(value).toLocaleString('ko-KR', {
        month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
        second: '2-digit', hour12: false
    });
    const rangeText = recent.length
        ? `${recent.length}건 · ${formatTime(recent[0].inspected_at)} ~ ${formatTime(recent[recent.length - 1].inspected_at)}`
        : '저장된 검사 결과가 없습니다.';
    if (range.textContent !== rangeText) range.textContent = rangeText;

    const signature = JSON.stringify(recent);
    if (signature === recentInspectionSignature) return;
    trendChart.data.labels = recent.map((row) => `${row.id}번`);
    trendChart.data.datasets[0].data = recent.map((row) => row.state === 'PASS' ? 1 : 0);
    trendChart.update();
    recentInspectionSignature = signature;
}

async function fetchInspectionImages() {
    try {
        const response = await fetch('/inspection/images');
        if (!response.ok) throw new Error(`저장 이미지 조회 실패: ${response.status}`);

        const images = await response.json();
        const currentModalImageUrl = imageModal.open
            ? inspectionImages[currentModalImageIndex]?.url
            : null;
        inspectionImages = images;
        if (currentModalImageUrl) {
            currentModalImageIndex = inspectionImages.findIndex(
                (item) => item.url === currentModalImageUrl
            );
        }
        const tableBody = document.getElementById('inspection-image-list');
        tableBody.replaceChildren();

        if (images.length === 0) {
            const row = document.createElement('tr');
            const cell = document.createElement('td');
            cell.colSpan = 3;
            cell.className = 'empty-row';
            cell.textContent = '저장된 이미지가 없습니다.';
            row.appendChild(cell);
            tableBody.appendChild(row);
            return;
        }

        for (const [index, item] of images.entries()) {
            const row = document.createElement('tr');
            const stateCell = document.createElement('td');
            const badge = document.createElement('button');
            badge.type = 'button';
            badge.className = `result-badge history-open-button ${item.state.toLowerCase()}`;
            badge.textContent = item.state;
            badge.setAttribute('aria-label', `${item.state} 검사 이력 열기`);
            badge.setAttribute('aria-haspopup', 'dialog');
            badge.addEventListener('click', () => openHistoryModal(item.state));
            stateCell.appendChild(badge);

            const imageCell = document.createElement('td');
            const link = document.createElement('button');
            link.type = 'button';
            link.className = 'inspection-image-button';
            link.setAttribute('aria-label', `${item.state} ${item.saved_at} 이미지 확대`);
            link.setAttribute('aria-haspopup', 'dialog');
            link.addEventListener('click', () => openInspectionImage(index));
            const preview = document.createElement('img');
            preview.className = 'inspection-thumbnail';
            preview.src = item.url;
            preview.alt = `${item.state} 검사 이미지`;
            link.appendChild(preview);
            imageCell.appendChild(link);

            const timeCell = document.createElement('td');
            timeCell.textContent = item.saved_at;
            row.append(stateCell, imageCell, timeCell);
            tableBody.appendChild(row);
        }
    } catch (error) {
        console.error(error);
    }
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

        const data = await response.json();
        updateSideControl(data);
        displayInspectionResult(data);
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

function updateCameraBadge(data) {
    const statuses = {
        live: ['LIVE', '카메라 영상 수신 중'],
        connecting: ['CONNECTING', '카메라 연결 중'],
        reconnecting: ['RECONNECTING', '영상 수신이 멈춰 카메라 재연결 대기 중'],
        offline: ['OFFLINE', '카메라 연결 끊김'],
        paused: ['LIVE · 검사 중단', '카메라 영상 수신 중 · 자동검사 중단'],
        'server-offline': ['SERVER OFFLINE', '서버에 연결할 수 없습니다.']
    };
    let state = data.camera_state;
    if (!(state in statuses)) state = 'connecting';
    if (state === 'live' && data.inspection_enabled === false) state = 'paused';
    const badge = document.getElementById('camera-status-badge');
    const label = document.getElementById('camera-status-label');
    const [text, description] = statuses[state];
    if (label.textContent !== text) label.textContent = text;
    badge.dataset.state = state;
    badge.title = description;
}

async function fetchLatestInspection() {
    if (isPolling) return;
    isPolling = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    let receivedInspection = false;
    try {
        const response = await fetch('/inspection', { signal: controller.signal, cache: 'no-store' });
        if (!response.ok) {
            throw new Error(`결과 조회 실패: ${response.status}`);
        }

        const data = await response.json();
        receivedInspection = true;
        updateCameraBadge(data);
        displayInspectionResult(data);
        updateInspectionControl(data);
        updateSideControl(data);
        updateRecentInspectionChart(data.recent_inspections);
        document.getElementById('total-count').textContent = data.check_number;
        document.getElementById('pass-count').textContent = data.pass_count;
        document.getElementById('fail-count').textContent = data.fail_count;
        document.getElementById('fail-rate').textContent = `${data.fail_rate}%`;
        document.getElementById('model-name').textContent = data.model_name;
        document.getElementById('device-name').textContent = data.device_name;

        if (data.inspection_id > lastInspectionId) {
            if (data.state === 'PASS' || data.state === 'FAIL') {
                updateAnomalyChart(data);
            }
            fetchInspectionImages();
            lastInspectionId = data.inspection_id;
            console.log('자동 검사 결과:', data);
        }
    } catch (error) {
        if (!receivedInspection) {
            updateCameraBadge({ camera_state: 'server-offline' });
            document.getElementById('recent-inspection-range').textContent = '최근 검사 결과를 갱신하지 못했습니다.';
        }
        const resultElement = document.getElementById('result-value');
        resultElement.textContent = '검사 결과를 불러오지 못했습니다.';
        resultElement.style.color = '#ef5964';
        console.error(error);
    } finally {
        clearTimeout(timeout);
        isPolling = false;
    }
}

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

fetchLatestInspection();
fetchInspectionImages();
setInterval(fetchLatestInspection, 500);
