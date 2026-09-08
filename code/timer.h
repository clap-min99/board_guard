#ifndef TIMER_H
#define TIMER_H

#include "stm32f4xx.h"

void Sensor_Timer_Init(void);
uint32_t Timer2_Micros(void);
void Timer2_Arm_CC1(uint32_t delay_us);
void Timer2_Arm_CC2(uint32_t delay_us);
void Timer2_Arm_CC3(uint32_t delay_us);
void Timer2_Cancel_CC1(void);
void Timer2_Cancel_CC2(void);
void Timer2_Cancel_CC3(void);
void Timer2_Timeout_Start(uint32_t delay_us);
void Timer2_Timeout_Cancel(void);
int Timer2_Timeout_Expired(void);
void Timer_Wait_Ms(uint32_t delay_ms);

void Timer2_CC1_Callback(void);
void Timer2_CC2_Callback(void);
void Timer2_CC3_Callback(void);

#endif
