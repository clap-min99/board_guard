
# 보드가드

> **PCB 불량품 확인형 시스템**  

컨베이어 벨트 위에 올라와 있는 PCB를 카메라로 양품/불량품으로 판독하여 불량품은 불량 결과를 확인하여 기록 후 제거

## Code

| Branch | 설명 | 담당 |
| --- | --- | --- |
| front | [MIDDLE](https://github.com/clap-min99/board_guard/tree/front) | 이양배 |
| hm | [WEB](https://github.com/clap-min99/board_guard/tree/hm) | 곽혜민 |
| mcu_m4 | [MCU](https://github.com/clap-min99/board_guard/tree/mcu_m4) | 이양배 |
| patchcore | [AI](https://github.com/clap-min99/board_guard/tree/patchcore) | 박수민, 김태환 |
| yolo | [AI](https://github.com/clap-min99/board_guard/tree/yolo) | 박수민, 김태환 |


## Contributors

| 이름 | GitHub | 담당 |
| --- | --- | --- |
| 박수민 | | 팀장|
| 김태홤 | | |
| 곽혜민 | | |
| 이양배 | | |

## 개발 목표

1. PCB 불량품 판독
2. 불량 원인 판독


## 핵심 특징

| 특징 | 설명 |
| --- | --- |
| ㅇ--- | ㅇ--- |



## 시스템 구성

```text
관리자 스마트폰
       │
       │ Local Web / HTTP :5000
       ▼
┌────────────────────────────────────┐
│         JETSON ORIN NANO           │
│                                    │
│  Flask Web                         │
│  양품 불량품 판정                  │
│  AI                               │
└────────────────┬───────────────────┘
                 │
                 │ GPIO PIN 10, 12 HIGH
                 ▼
┌────────────────────────────────────┐
│           M4 NUCLEAR64             │
│                                    │
│  서보, 스테핑모터 제어              │
│  LED, BUZZER 제어                  │
└────────────────┬───────────────────┘
                 │
                 ▼
       불량품 배출 및 컨베이어 벨트 이동
```

### 역할 분리

| 구분 | 담당 기능 |
| --- | --- |
| JETSON ORIN NANO | 관리자 Web, 판단 |
| M4 NUCLEAR64 | 스테핑모터, 서보, LED, 실시간 상태 제어, 부저 |

## 동작 과정

0. 컨베이어 벨트 동작
1. 카메라에 PCB 등장
2. 양품 불량품 판독
3. 불량 원인 판독
4. 불량품 라인에서 배출

## 개발 환경

### Hardware

| 구분 | 구성 |
| --- | --- |
| Controller | JETSON ORIN NANO, M4 NUCLEAR64 |
| Stepper Motor | 28BYJ-48 ×1 |
| Motor Driver | ULN2003 ×1 |
| Servo Motor | MG90S ×1 |
| LED | x2 |
| BUZZER | ×1 |

### Software

| 영역 | 구성 |
| --- | --- |
| JETSON ORIN NANO OS | 64-bit, ? |
| Application | Python, Flask 3.1.3 |
| M4 NUCLAER64 | Embedded C, Visual Studio |

## 주요 기능

### Local Web

- view

## 프로젝트 구조

```text
board_guard/
├── JETSON_ORIN_NANO/
│   └── WEB
│        ├──  engine....
│
│   └── AI
│        ├── flask.py......
│
│
│
└── M4_NUCLEAR64/
    ├── main.c.......

```

## 구현 검증

| 시험 항목 | 판정 기준 | 결과 |
| --- | --- | --- |


