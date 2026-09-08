#ifndef SENSOR_CONTROL_H
#define SENSOR_CONTROL_H

#define SENSOR_ERROR (-1)

void Sensor_Control_Init(void);

void led_control(int on);
void alarm_control(int on);
int Alarm_Is_Playing(void);

#endif
