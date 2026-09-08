

# 설계

# 0. 범위 / 전제

- 기반 : M4 Nuclear64
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
JETSON ORIN NANO Developer Kit           M4 Nuclear64  
─────────────────                       ─────────────────
양품 불량품 판단                        상태머신,
                                       모터/LED 실시간 제어
```

## M4 Nuclear64 PIN MAP
| 장치 | 핀 | 설정 | AF 필요여부 | 완료 여부 |
| --- | --- | --- | --- | --- |
| LED(綠) | PA4 | GPIO Output | 불필요 | 완료 |
| LED(赤) | PA0 | GPIO Output | 불필요 | 완료 |
| 부저 | PB4 | TIM3_CH1_PWM | AF2 | 완료 |
| 스탭모터 4핀 | PC7/PB6/PA7/PA6 | GPIO Output | 불필요 | 미사용 |
| 스탭모터 2핀 | PA6(PUL)/PA7(DIR) | GPIO Output | 불필요 | 완료 |
| 서보모터 | PB5 | TIM3_CH2_PWM | AF2 | 미완료 |
| jetson(STOP) | P29 - PC10 | GPIO Input | 불필요 | 인터럽트 완료 |
| jetson(PASS->MOVE) | P31 - PC11 | GPIO Input | 불필요 | 인터럽트 완료 |
| jetson(PAIL->MOVE) | P33 - PC12 | GPIO Input | 불필요 | 인터럽트 완료 |

# 2. 상태 및 이벤트

```
typedef enum {
      STATE_RUN
          컨베이어 동작 중
      STATE_INSPECT
          컨베이어 정지 + Jetson 검사 중
      STATE_FAIL
          FAIL 처리 중
} SystemState;

EVENT_STOP()
EVENT_PASS()
EVENT_FAIL()
```

# 2.1 부팅 동작

```
전원 인가  
    → 주변장치 초기화
    → IDLE 상태 대기
    → 컨베이어 벨트 동작
```

# 2.2 상태 규칙
| 상태 | 진입 | 허용 입력 | 전이 |
| --- | --- | --- | --- |

# 2.3 이벤트 동작 규칙
| 이벤트 | 동작 |
| --- | --- | 
| EVENT_STOP | 컨베이어 벨트 정지 |
| EVENT_PASS | 컨베이어 벨트 시작 |
| EVENT_FAIL | 서보모터 동작 |

장치를 직접 조작하지 않고 반드시 장치 함수를 호출하여 조작하게끔 만든다.
# 2.4  구조
```
                  전원 ON
                     ↓
                 STATE_RUN
                     │
                     │ PC10(STOP)
                     ▼
               STATE_INSPECT
                  /       \
         PC11(완료)       PC12(FAIL)
              │               │
              │               ▼
              │           STATE_FAIL
              │               │
              │           Servo 처리
              │               │
              │          PC11(완료)
              │               │
              └───────┬───────┘
                      ▼
                  STATE_RUN
```
# 2.5 흐름

```
Jetson GPIO
    ↓
EXTI ISR
    ↓
PASS 또는 FAIL 이벤트를 Queue에 저장
    ↓
main 반복문{
    초기화(최초)
      ↓
초기 상태 진입(최초)
      ↓
   무한 반복
Queue에 이벤트가 있으면 상태머신에 전달
없으면 다음 이벤트 대기      
}      
    ↓
Queue에서 이벤트를 꺼냄
    ↓
현재 상태 함수에 전달
    ↓
상태 전이 및 장치 함수 호출
````
# 2.5.1 PASS 흐름
```
① 부팅
   ↓
STATE_RUN
   ↓
Step_Motor_Run()

② PCB가 ROI 80% 진입

Jetson P29
→ STM32 PC10
→ EXTI10
→ STOP 이벤트

③ STATE_INSPECT

Step_Motor_Stop()

④ Jetson 60 frame 검사

⑤ PASS

Jetson P31
→ STM32 PC11
→ PASS 이벤트

⑥ STATE_RUN

Step_Motor_Run()
```

# 2.5.2 FAIL 흐름
```
① STATE_RUN
   ↓
PCB 진입

② P29 → PC10

STOP
↓
STATE_INSPECT
↓
컨베이어 정지

③ 60 frame 검사

④ FAIL 확정

P33 → PC12
↓
FAIL 이벤트
↓
STATE_FAIL

⑤ 빨간 LED
   부저
   Servo PUSH
   Servo HOME

⑥ Jetson P31 → PC11

RESUME
↓
STATE_RUN
↓
컨베이어 재가동
```
# 3. 스탭모터

| 항목 | 결정 내용 |
| --- | --- |
| 모터/드라이버 | bq stepping motor 42shdb4036z-24b + TB6600 microstep driver |
| 핀 | PA6(PUL)/PA7(DIR) (동작 / 방향) |
| 구동 방식 | Full Drive (2상 Bipolar Stepper) |
| 속도 제어 방식 | 스텝 간 딜레이 조절로 속도 제어 → 1ms |
| 호출 | 1회 호출시 특정 스탭 만큼 회전 |

~~| 모터/드라이버 | 28BYJ-48 + ULN2003 |~~
~~| 핀 | PC7/PB6/PA7/PA6 (PORTA nibble 분할 제어) |~~
~~| 구동 방식 | Full Drive (2상 여자, 4-step 시퀀스) |~~
~~| 속도 제어 방식 | 스텝 간 딜레이 조절로 속도 제어 → 3ms |~~
~~| 호출 | 1회 호출시 특정 스탭 만큼 회전 |~~

# 4. 서보 모터

| 항목 | 결정 내용 |
| --- | --- |
| 모델 | MG90S |
| 핀/PWM | PB5, TIM3_CH2_PWM |
| 호출 | 1회 호출시 특정 각도만큼 회전 후 복귀 |

# 5. LED

| 항목 | 결정 내용 |
| --- | --- |
| 赤 | EVENT_FAIL 발생 시 5초간 점등 |
| 綠 | EVENT_NORMAL 발생 시 5초간 점등 |
| `None` | --- |

# 5. BUZZER

| 항목 | 결정 내용 |
| --- | --- |
| On | EVENT_FAIL 발생 시 특정알람 |
| `None` | --- |



# 6. 검증

1. 젠슨과 아트메가 그라운드 연결 필수임
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


