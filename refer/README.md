# 설계

# 0. 범위 / 전제

- 기반 :STM32F411RE Nucleo-64
- 대상  
      상태머신  
      스탭모터 ( 컨베이어 벨트 묘사 )  
      서보모터 ( 정상 비정상 분류 )  
      LED ( 정상 비정상 시각적 표현)  

- 기반 : JETSON ORIN NANO Developer Kit  
- 대상     
      GPIO PIN 제어

# 1. 시스템 구성 및 하드웨어 리소스 배정
```
JETSON ORIN NANO Developer Kit          STM32F411RE Nucleo-64 
─────────────────                       ─────────────────
양품 불량품 판단                        상태머신,
                                       모터/LED 실시간 제어
```

## STM32F411RE Nucleo-64 PIN MAP
| 장치 | 핀 | 설정 | AF 필요여부 | 완료 여부 |
| --- | --- | --- | --- | --- |
| LED(綠) | PA4 | GPIO Output | 불필요 | 완료 |
| LED(赤) | PA0 | GPIO Output | 불필요 | 완료 |
| 부저 | PB4 | TIM3_CH1_PWM | AF2 | 완료 |
| ~~스탭모터 4핀~~ | PC7/PB6/PA7/PA6 | GPIO Output | 불필요 | 미사용 |
| 스탭모터 2핀 | PA6(PUL)/PA7(DIR) | GPIO Output | 불필요 | 완료 |
| 서보모터 | PB5 |GPIO Output/ TIM2 CC2 compare interrupt timing| 불필요 | 미완료 |
| jetson(STOP) | P29 - PC10 | GPIO Input | 불필요 | 인터럽트 완료 |
| jetson(PASS) | P31 - PC11 | GPIO Input | 불필요 | 인터럽트 완료 |
| jetson(FAIL) | P33 - PC12 | GPIO Input | 불필요 | 인터럽트 완료 |

# 2. 상태 및 이벤트

```
typedef enum {
      STATE_RUN
          컨베이어 동작 중
      STATE_INSPECT
          컨베이어 정지 + Jetson 검사 중
      STATE_REJECT
          FAIL 처리 중
} SystemState;

EVT_STOP
EVT_PASS
EVT_FAIL
EVT_REJECT_DONE
EVT_DISPLAY_TIMEOUT

```

# 2.1 부팅 동작

```
전원 인가  
    → 주변장치 초기화
    → 컨베이어 벨트 동작
```

# 2.3 상태 규칙
|상태	|의미|
|---|---|
|STATE_RUN	|컨베이어가 계속 움직이는 상태|
|STATE_INSPECT	|컨베이어를 멈추고 Jetson 결과를 기다리는 상태|
|STATE_REJECT	|불량 PCB를 서보로 배출하는 상태|

# 2.4 상태별 동작 규칙
|현재 상태	|진입 동작	|이벤트	|처리|
|---|---|---|---|
|STATE_RUN	|Step_Motor_Run()	|EVT_STOP	|STATE_INSPECT 전이|
|STATE_INSPECT	|Step_Motor_Stop()	|EVT_PASS	|초록 LED·타이머 시작 후 STATE_RUN|
|STATE_INSPECT	|Step_Motor_Stop()	|EVT_FAIL	|STATE_REJECT 전이|
|STATE_REJECT	|빨간 LED·부저·서보 시작	|EVT_REJECT_DONE	|부저 OFF 후 STATE_RUN|
|전체	|없음	|EVT_DISPLAY_TIMEOUT	|LED만 OFF|

# 2.5 이벤트 규칙
|이벤트|발생 위치|의미|
|---|---|---|
|EVT_STOP	|EXTI10 ISR	|PCB가 검사 위치에 도착했으므로 컨베이어 정지|
|EVT_PASS	|EXTI11 ISR	|Jetson이 양품으로 판정|
|EVT_FAIL	|EXTI12 ISR	|Jetson이 불량품으로 판정|
|EVT_REJECT_DONE	|서보 제어 완료 시	|PUSH와 HOME 동작 완료|
|EVT_DISPLAY_TIMEOUT	|타이머 만료 시	|결과 LED 5초 표시 종료|

장치를 직접 조작하지 않고 반드시 장치 함수를 호출하여 조작하게끔 만든다.

# 2.6  구조
```
                  JETSON GPIO
                     ↓
                 EXTI ISR      Timer*servo 완료
                     │                │
                     │    ┬───────────┘
                     ▼    ▼
               Event Queue
                     │
                     ▼
             main event loop
                     │
                     ▼
            system state machine
                     │
                     ▼
            device control API
```
# 2.6.1 구조 구성요소간 각 역할
```
EXTI ISR
Pending bit 확인
해당 Pending bit 제거
EVT_STOP, EVT_PASS, EVT_FAIL 중 하나를 Queue에 저장
즉시 복귀

EXTI ISR은 상태를 직접 바꾸지 않습니다.

Event Queue
ISR이 이벤트를 넣는 장소
고정 크기 배열 기반
동적 메모리 사용 없음
ISR이 생산자, main이 소비자
main Event Loop

초기화와 상태 초기 진입은 한 번만 수행합니다.

이후 무한 반복에서는:

Queue에서 이벤트 확인
이벤트가 있으면 꺼냄
현재 상태 함수에 전달
상태 함수가 장치 API 호출 또는 상태 전이
```

# 각 실제시간 흐름 예시

## PASS 흐름
```
① 부팅
   → 주변장치 초기화
   → STATE_RUN 진입
   → Step_Motor_Run()

② PCB가 ROI 검사 위치에 도착

③ Jetson BOARD 29 HIGH
   → STM32 PC10 / EXTI10
   → EVT_STOP을 Queue에 저장

④ main이 EVT_STOP 처리
   → Step_Motor_Stop()
   → STATE_INSPECT 전이

⑤ Jetson 60프레임 검사

⑥ PASS 확정
   → Jetson BOARD 31 HIGH
   → STM32 PC11 / EXTI11
   → EVT_PASS를 Queue에 저장

⑦ STATE_INSPECT에서 EVT_PASS 처리
   → 빨간 LED OFF
   → 초록 LED ON
   → 5초 표시 타이머 시작
   → STATE_RUN 전이
   → Step_Motor_Run()

⑧ 5초 후 EVT_DISPLAY_TIMEOUT
   → 초록 LED OFF
```
## FAIL 흐름
```
① STATE_RUN에서 PCB 진입

② Jetson BOARD 29 HIGH
   → EVT_STOP
   → STATE_INSPECT
   → 컨베이어 정지

③ Jetson 60프레임 검사

④ FAIL 확정
   → Jetson BOARD 33 HIGH
   → STM32 PC12 / EXTI12
   → EVT_FAIL을 Queue에 저장

⑤ STATE_INSPECT에서 EVT_FAIL 처리
   → STATE_REJECT 전이

⑥ STATE_REJECT 진입
   → 초록 LED OFF
   → 빨간 LED ON
   → 부저 ON
   → Servo PUSH 시작

⑦ Servo PUSH 완료
   → Servo HOME 시작

⑧ Servo HOME 완료
   → EVT_REJECT_DONE을 Queue에 저장

⑨ STATE_REJECT에서 EVT_REJECT_DONE 처리
   → 부저 OFF
   → STATE_RUN 전이
   → Step_Motor_Run()

⑩ 5초 후 EVT_DISPLAY_TIMEOUT
   → 빨간 LED OFF
```

# 3. 스탭모터

| 항목 | 결정 내용 |
| --- | --- |
| 모터/드라이버 | bq stepping motor 42shdb4036z-24b + TB6600 microstep driver |
| 핀 | PA6(PUL)/PA7(DIR) (동작 / 방향) |
| 구동 방식 | TB6600 PUL/DIR 인터페이스, TIM4 기반 STEP 펄스 생성 |
| 속도 제어 방식 | 스텝 간 딜레이 조절로 속도 제어 |

~~| 모터/드라이버 | 28BYJ-48 + ULN2003 |~~
~~| 핀 | PC7/PB6/PA7/PA6 (PORTA nibble 분할 제어) |~~
~~| 구동 방식 | Full Drive (2상 여자, 4-step 시퀀스) |~~
~~| 속도 제어 방식 | 스텝 간 딜레이 조절로 속도 제어 → 3ms |~~
~~| 호출 | 1회 호출시 특정 스탭 만큼 회전 |~~

# 4. 서보 모터

| 항목 | 결정 내용 |
| --- | --- |
| 모델 | MG90S |
| 핀/PWM | PB5, GPIO(TIM2 CC2 비교 인터럽트가 다음 HIGH/LOW 전환 시점을 예약) |
| 호출 | 1회 호출시 특정 각도만큼 회전 |

# 5. LED

| 항목 | 결정 내용 |
| --- | --- |
| 赤 | EVT_FAILL 발생 시 5초간 점등 |
| 綠 | EVT_PASS 발생 시 5초간 점등 |
| `None` | --- |

# 6. BUZZER

| 항목 | 결정 내용 |
| --- | --- |
| On | EVT_FAIL 발생 시 특정알람 |
| `None` | --- |



# 7. 검증

1. 젠슨과 STM32 GND → Jetson과 STM32 GND
2. 젠슨 gpio 정상 동작 10번, 11번, 12번 인터럽트까지 확인.

## JETSON ORIN NANO gpio pin setting

### 입력

```
sudo /opt/nvidia/jetson-io/jetson-io.py
```
#### 설정
```
Configure Jetson 40pin Header
    ↓
Configure header pins manually
    ↓
제어하고자 하는 핀
    ↓
모드 설정 GPIO
    ↓
Save pin changes
    ↓
Save and reboot
```

### sample ex code

```
import Jetson.GPIO as GPIO
import time
GPIO.setmode(GPIO.BOARD)
GPIO.setup(12, GPIO.OUT)
GPIO.output(12, GPIO.HIGH)
time.sleep(100)
GPIO.output(12, GPIO.LOW)
GPIO.cleanup()
```


### 의식의 흐름


