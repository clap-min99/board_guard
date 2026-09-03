"""
capture_empty_reference.py

조명박스 안에 아무것도 안 놓은 "빈 배경" 상태를 기준(reference) 사진으로 저장한다.
이 사진은 이후 camera_app.py에서 "보드가 있는지 없는지(MISSING)" 판별에 쓰인다.

사용법:
    1. 조명박스 안에서 보드를 치운다 (완전히 빈 상태)
    2. python3 capture_empty_reference.py 실행
    3. 미리보기 보면서 space 눌러 저장, q로 종료

주의: 조명/카메라 위치가 바뀌면 이 기준 사진도 다시 찍어야 한다.
"""

import time

import cv2

CAMERA_URL = "http://192.168.21.50:8080/video"   # 오늘 IP Webcam 주소로 수정
OUTPUT_PATH = "empty_reference.jpg"
SPACE_KEY = ord(" ")


def main() -> None:
    cap = cv2.VideoCapture(CAMERA_URL)
    if not cap.isOpened():
        raise RuntimeError("카메라를 열 수 없습니다.")

    print("조명박스를 완전히 비운 상태에서 space를 눌러 저장하세요. q: 종료")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue

            preview = frame.copy()
            cv2.putText(
                preview, "EMPTY REFERENCE - space: save, q: quit", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 200), 2, cv2.LINE_AA,
            )
            cv2.imshow("Empty Reference", preview)

            key = cv2.waitKey(1) & 0xFF
            if key == SPACE_KEY:
                cv2.imwrite(OUTPUT_PATH, frame)
                print(f"저장됨: {OUTPUT_PATH}")
            elif key == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()