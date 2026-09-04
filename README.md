## 핀맵

| 장치 | 핀 | 설정 | AF 필요여부 |
| --- | --- | --- | --- |
| LED(綠) | PA4 | GPIO Output | 불필요 |
| LED(赤) | PB8 | GPIO Output | 불필요 |
| 부저 | PB4 | TIM3_CH1_PWM | AF2 |
| 스탭모터 4핀 | PC7/PB6/PA7/PA6 | GPIO Output | 불필요 |
| 서보모터 | PB5 | TIM3_CH2_PWM | AF2 |


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

# 0. 
