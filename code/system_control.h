#ifndef SYSTEM_CONTROL_H
#define SYSTEM_CONTROL_H

typedef enum{
    STATE_RUN,
    STATE_INSPECT,
    STATE_REJECT
}STATE_MACHINE;

void _state_machine_init();
void main_state_machine(SystemEvent event);

#endif
