#ifndef STEP_MOTOR_H
#define STEP_MOTOR_H

void Step_Motor_Init(void);
void step_motor_control(int position_percent);
int Step_Motor_Is_Moving(void);
void Step_Motor_Run(void);
void Step_Motor_Stop(void);
void Step_Motor_Run_Reverse(void);


#endif
