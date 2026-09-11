#ifndef EVENT_QUEUE_H
#define EVENT_QUEUE_H

typedef enum {
    EVT_STOP,
    EVT_PASS,
    EVT_FAIL,
    EVT_REJECT_DONE,
    EVT_DISPLAY_TIMEOUT,
    EVT_MOTOR_DONE,
    EVT_SERVO_DONE
} SystemEvent;

void EventQueue_Init(void);
int EventQueue_Push(SystemEvent event);
int EventQueue_Pop(SystemEvent *event);

#endif
