

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
| 장치 | 핀 | 설정 | AF 필요여부 |
| --- | --- | --- | --- |
| LED(綠) | PA4 | GPIO Output | 불필요 |
| LED(赤) | PB8 | GPIO Output | 불필요 |
| 부저 | PB4 | TIM3_CH1_PWM | AF2 |
| 스탭모터 4핀 | PC7/PB6/PA7/PA6 | GPIO Output | 불필요 |
| 서보모터 | PB5 | TIM3_CH2_PWM | AF2 |
| jetson(양품) | PC10 | GPIO Input | 불필요 |
| jetson(불량품) | PC12 | GPIO Input | 불필요 |

## M4 Nuclear64 PIN MAP
| 상태 | 핀 | 설정 |
| --- | --- | --- | 
| 양품 | 11 | GPIO Output |
| 불량품 | 12 | GPIO Output |

# 2. 상태 및 이벤트

```
typedef enum {
    STATE_IDLE,
    STATE_NORMAL,
    STATE_FAIL,
} SystemState;

EVENT_IDLE()
EVENT_NORMAL()
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
| STATE_IDLE | 최초 부팅, 이벤트가 없을 경우 | pc10, pc12 | PC10(양품) ▷ STATE_NORMAL PC12(불량품) ▷ STATE_FAIL |
| STATE_NORMAL | PC10 INTERRUPT  | `None` | STATE_IDLE |
| STATE_FAIL | PC12 INTERRUPT  | `None` | STATE_IDLE |

# 2.3 이벤트 동작 규칙
| 이벤트 | 동작 |
| --- | --- | 
| EVENT_IDLE | 스탭모터 ▷ One cycle |
| EVENT_NORMAL | LED(綠) ▷ On |
| EVENT_FAIL | LED(赤) ▷ On, 서보모터 ▷ One cycle, 부저 ▷ On |

장치를 직접 조작하지 않고 반드시 장치 함수를 호출하여 조작하게끔 만든다.

# 2.4 전체 흐름

```
1. 최초 부팅 STATE_IDLE 스탭모터 ▷ One cycle
2. PCB 판단 시작
    2.1 양품 결정 
        2.1.1 JETSON PIN10 GPIO HIGH - > (PC10 INTERRUPT)
        2.1.2 STATE_NORMAL 진입, Queue에 이벤트 push
        2.1.3 Queue 읽고 이벤트 동작(LED(赤) ▷ OFF, LED(綠) ▷ On)

    2.2 불량품 결정 (PC12 INTERRUPT)
        2.2.1 JETSON PIN12 GPIO HIGH - > (PC12 INTERRUPT)
        2.2.2 STATE_FAIL 진입, Queue에 이벤트 push
        2.2.3 Queue 읽고 이벤트 동작(LED(綠) ▷ OFF, LED(赤) ▷ On, 서보모터 ▷ One cycle, 부저 ▷ On)

3. 대기 상태 복귀(STATE_IDLE) 스탭모터 ▷ One cycle
````

# 3. 스탭모터

| 항목 | 결정 내용 |
| --- | --- |
| 모터/드라이버 | 28BYJ-48 + ULN2003 |
| 핀 | PC7/PB6/PA7/PA6 (PORTA nibble 분할 제어) |
| 구동 방식 | Full Drive (2상 여자, 4-step 시퀀스) |
| 속도 제어 방식 | 스텝 간 딜레이 조절로 속도 제어 → 3ms |
| 호출 | 1회 호출시 특정 스탭 만큼 회전 |

    ```
    // IN1,IN2,IN3,IN4 순서 (PA0-PA3 / PA4-PA7 nibble)
    const uint8_t FULL_DRIVE_SEQ[4] = {
        0b1100,
        0b0110,
        0b0011,
        0b1001
    };
    ```

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
2. 젠슨 gpio 정상 동작 11번 12번 인터럽트까지 확인.

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
