#ifndef SYSTEM_CONTROL_H
#define SYSTEM_CONTROL_H

#include "event_queue.h"

typedef enum {
    STATE_RUN,
    STATE_INSPECT,
    STATE_REJECT,       /* 연속회전 및 정지 완료 대기 */
    STATE_REJECT_MOVE,  /* 배출 위치로 이송 중 */
    STATE_SERVO_STOP    /* 시작 시 중립 PWM 안정화 대기 */
} STATE_MACHINE;

void _state_machine_init(void);
void main_state_machine(SystemEvent event);

#endif
