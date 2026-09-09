#include "timer.h"
#include "step_motor.h"
#include "alarm.h"
#include "led.h"
#include "jetson.h"
#include "sensor_control.h"
#include "servo.h"

void Sensor_Control_Init(void)
{
	Sensor_Timer_Init();
	LED_Init();
	Step_Motor_Init();
	Alarm_Init();
	jetson_init();
	Servo_Init();
}
