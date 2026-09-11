#include "system_control.h"
#include "event_queue.h"
#include "device_driver.h"
#include "servo.h"

#define PCB_GET_OUT 1300

STATE_MACHINE _state;

void _state_machine_init(void)
{
    Step_Motor_Stop();
    _state = STATE_SERVO_STOP;
    /* 연속회전형에서 Home은 원점 이동이 아니라 중립 PWM 정지이다. */
    Servo_Home();
}

void main_state_machine(SystemEvent event)
{
    switch (_state) {
    case STATE_RUN:
        if (event == EVT_STOP) {
            Step_Motor_Stop();
            _state = STATE_INSPECT;
        }
        break;

    case STATE_INSPECT:
        if (event == EVT_PASS) {
            LED_RED_Off();
            LED_GREEN_ON();
            _state = STATE_RUN;
            Step_Motor_Run();
        } else if (event == EVT_FAIL) {
            LED_GREEN_Off();
            LED_RED_ON();
            _state = STATE_REJECT_MOVE;
            Step_Motor_Run_Steps(PCB_GET_OUT);
        }
        break;

    case STATE_REJECT_MOVE:
        /* 추가 PASS/FAIL/STOP은 무시하고 이송 완료만 기다린다. */
        if (event == EVT_MOTOR_DONE) {
            _state = STATE_REJECT;
            Servo_Push();
        }
        break;

    case STATE_REJECT:
    case STATE_SERVO_STOP:
        /* Servo_Push는 회전 후 중립 정지까지 마친 다음 완료를 보낸다. */
        if (event == EVT_SERVO_DONE) {
            LED_RED_Off();
            _state = STATE_RUN;
            Step_Motor_Run();
        }
        break;

    default:
        break;
    }
}
