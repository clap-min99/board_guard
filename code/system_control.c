#include "system_control.h"
#include "event_queue.h"


#define PCB_GET_OUT 1000
/*
event result
STOP = 0
PASS = 1
FAIL = 2
REJECT = 3
TIMEOUT = 4

typedef enum{
    STATE_RUN,
    STATE_INSPECT,
    STATE_REJECT
}STATE_MACHINE;
*/

STATE_MACHINE _state;

void _state_machine_init(){
    _state = STATE_RUN;
}

void main_state_machine(SystemEvent event){
    switch(_state){
        case STATE_RUN:
            if(event == EVT_STOP){
                Step_Motor_stop();
                _state = STATE_INSPECT;
            }
            break;

        case STATE_INSPECT:
            // 지금 상태는 벨트를 멈추고 젯슨결과를 기다리고 있따.
            switch(event){
                case EVT_PASS:
                    // 성공 시 다음꺼 확인
                    Step_Motor_RUN();
                    LED_RED_Off();
                    LED_GREEN_ON();
                    _state = STATE_RUN;
                    break;
                case EVT_FAIL:
                    // 실패시 컨베이어벨트 일정만큼만 돌리고
                    LED_GREEN_Off();
                    LED_RED_ON();
                    Step_Motor_Run_Steps(PCB_GET_OUT);
                    break;
                case EVT_MOTOR_DONE:
                    Servo_Push();
                    _state = STATE_REJECT;
                    break;
                default:
                    break;
            }
            break;

        case STATE_REJECT:
            if (event == EVT_SERVO_DONE){
                LED_RED_Off();
                Step_Motor_RUN();
                _state = STATE_RUN;
            }
            break;

        default:

            break;
    }
}