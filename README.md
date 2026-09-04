

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
| 양품 | 10 | GPIO Output |
| 불량품 | 12 | GPIO Output |

# 2. 상태 머신

```
typedef enum {
    STATE_IDLE,
    STATE_NORMAL
    STATE_FAIL
} SystemState;
```

# 2.1 부팅 동작

```
전원 인가  
    → 주변장치 초기화
    → IDLE 상태 대기
```

# 2.2 분기 조건
한 상태에 들어가면 영원히 있는가? IDLE만 영원히 있고 나머지는 GPIO신호가 들어올때만 수행한다?
| 상태 | 진입 동작 | 허용 입력 | 전이 |
| --- | --- | --- | --- |
| STATE_IDLE | 최초 부팅,  |  | PC10(양품) ▷ STATE_NORMAL PC12(불량품) ▷ STATE_FAIL |
| STATE_NORMAL | PC10 INTERRUPT  | LED(綠) ▷ On, 스탭모터 ▷ On | STATE_IDLE |
| STATE_FAIL | PC12 INTERRUPT  | LED(赤) ▷ On, 서보모터 ▷ On, 부저 ▷ On | STATE_IDLE |
