"""
capture_dataset.py

카메라(IP Webcam 스트림 또는 USB)를 계속 띄워두고,
스페이스바로 현재 프레임을 저장하는 데이터 수집 스크립트.

네트워크 스트림 지연을 막기 위해 별도 스레드에서 항상 최신 프레임만 유지한다.

폴더 구조:
    pcb_dataset/
    └── <BOARD>/
        ├── normal/
        │   ├── 0000.jpg
        │   └── ...
        └── abnormal/
            ├── 0000.jpg
            └── ...

키:
    space : 현재 프레임 저장
    n     : 정상(normal) 촬영 모드로 전환
    d     : 불량(abnormal) 촬영 모드로 전환
    q     : 종료

실행:
    python3 capture_dataset.py
    (아래 BOARD_NAME, CAMERA_URL만 상황에 맞게 코드에서 직접 수정)
"""

import os
import threading
import time

import cv2

# ============================================================
# 설정 - 여기만 상황에 맞게 바꿔서 쓰면 됨
# ============================================================

# BOARD_NAME = "hc_sr04"
BOARD_NAME = "hc_sr04_back"

# ⚠️ IP Webcam 앱 화면에 뜨는 실제 주소로 매번 바꿀 것
# (USB 테더링 재연결마다 IP가 바뀔 수 있음)
CAMERA_URL = "http://192.168.21.50:8080/video"

DATASET_ROOT = "pcb_dataset"

DISPLAY_WIDTH = 960
DISPLAY_HEIGHT = 720

SPACE_KEY = ord(" ")


# ============================================================
# 스트림 지연 방지 - 별도 스레드에서 항상 최신 프레임만 유지
# ============================================================

class LatestFrameReader:
    def __init__(self, src):
        self.cap = cv2.VideoCapture(src)
        self.frame = None
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self):
        while self.running:
            success, frame = self.cap.read()
            if success:
                with self.lock:
                    self.frame = frame

    def read(self):
        with self.lock:
            if self.frame is None:
                return False, None
            return True, self.frame.copy()

    def release(self):
        self.running = False
        self.thread.join()
        self.cap.release()


# ============================================================
# 폴더 준비
# ============================================================

def ensure_board_structure(board: str) -> dict:
    board_root = os.path.join(DATASET_ROOT, board)
    dirs = {
        "normal": os.path.join(board_root, "normal"),
        "abnormal": os.path.join(board_root, "abnormal"),
    }
    for path in dirs.values():
        os.makedirs(path, exist_ok=True)
    return dirs


def count_existing(out_dir: str) -> int:
    return len([f for f in os.listdir(out_dir) if f.lower().endswith((".jpg", ".png"))])


def next_index(out_dir: str) -> int:
    existing = [f for f in os.listdir(out_dir) if f.lower().endswith(".jpg")]
    if not existing:
        return 0
    numbers = []
    for f in existing:
        try:
            numbers.append(int(os.path.splitext(f)[0]))
        except ValueError:
            continue
    return max(numbers) + 1 if numbers else 0


# ============================================================
# 화면 표시
# ============================================================

def draw_status(frame, board, mode, count):
    color = (0, 200, 0) if mode == "normal" else (0, 0, 255)
    text = f"[{board}] mode: {mode.upper()}  saved: {count}"
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 40), (30, 30, 30), -1)
    cv2.putText(frame, text, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2, cv2.LINE_AA)
    cv2.putText(
        frame, "space: save   n: normal   d: abnormal   q: quit",
        (10, frame.shape[0] - 15),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA,
    )
    return frame


# ============================================================
# 메인 루프
# ============================================================

def main() -> None:
    dirs = ensure_board_structure(BOARD_NAME)
    indices = {mode: next_index(path) for mode, path in dirs.items()}

    mode = "normal"

    cap = LatestFrameReader(CAMERA_URL)
    cv2.namedWindow("Capture", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Capture", DISPLAY_WIDTH, DISPLAY_HEIGHT)

    print(f"보드: {BOARD_NAME}")
    for m, path in dirs.items():
        print(f"  {m}: {path}  (다음 번호: {indices[m]:04d})")
    print("space: 저장 / n: normal 모드 / d: abnormal 모드 / q: 종료")

    print("카메라 연결 대기 중...")
    for _ in range(50):
        success, _ = cap.read()
        if success:
            break
        time.sleep(0.1)
    else:
        print("[WARN] 카메라 프레임을 못 받아옴 - CAMERA_URL 확인 필요")

    try:
        while True:
            success, frame = cap.read()
            if not success:
                time.sleep(0.05)
                continue

            display = frame.copy()
            display = draw_status(display, BOARD_NAME, mode, count_existing(dirs[mode]))
            cv2.imshow("Capture", display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("n"):
                mode = "normal"
                print("[모드 전환] normal")
            elif key == ord("d"):
                mode = "abnormal"
                print("[모드 전환] abnormal")
            elif key == SPACE_KEY:
                idx = indices[mode]
                filename = os.path.join(dirs[mode], f"{idx:04d}.jpg")
                cv2.imwrite(filename, frame)
                indices[mode] += 1
                print(f"저장됨: {filename}  (누적 {indices[mode]}장)")
    finally:
        cap.release()
        cv2.destroyAllWindows()

    for m, path in dirs.items():
        print(f"{m}: 총 {count_existing(path)}장 -> {path}")


if __name__ == "__main__":
    main()