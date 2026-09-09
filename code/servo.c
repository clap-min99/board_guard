#include "device_driver.h"
#include "timer.h"
#include "servo.h"
#include <stdio.h>


#define SERVO_PERIOD_US        20000
#define SERVO_HOME_PULSE_US     2000
#define SERVO_PUSH_PULSE_US     1000
#define SERVO_REPEAT              10

#define servo_high 1
#define servo_low 0

static volatile int servo_state;
static volatile int servo_count;
static volatile int servo_pulse;

void Servo_Init(void){
	Macro_Set_Bit(RCC->AHB1ENR, 1);

	// 출력으로 설정하고 초기 OFF PB5
	Macro_Write_Block(GPIOB->MODER, 0x3, 0x1, 10);
	Macro_Clear_Bit(GPIOB->OTYPER, 5);
	Macro_Clear_Bit(GPIOB->ODR, 5); 

}

void Servo_Push(void){
	printf("servo push in \n");
	servo_pulse = SERVO_PUSH_PULSE_US;
	servo_count = 0;
	servo_state = servo_high;
	Macro_Set_Bit(GPIOB->ODR, 5);
	Timer2_Arm_CC2(servo_pulse);
}

void Servo_Home(void){
	servo_pulse = SERVO_HOME_PULSE_US;
	servo_count = 0;
	servo_state = servo_high;
	Macro_Set_Bit(GPIOB->ODR, 5);
	Timer2_Arm_CC2(servo_pulse);
}

void Timer2_CC2_Callback(void)
{
	/* state가 high인가? */
	if(servo_state == servo_high){
		servo_state = servo_low;
		Macro_Clear_Bit(GPIOB->ODR, 5);
		/* 남은시간? 어케?*/
		Timer2_Arm_CC2(SERVO_PERIOD_US - servo_pulse);
	}
	/* state가 low인가? */
	else{
		servo_count++;
		if(servo_count < SERVO_REPEAT){
			servo_state = servo_high;
			Macro_Set_Bit(GPIOB->ODR, 5);
			/* 남은시간?*/
			Timer2_Arm_CC2(servo_pulse);
		}else{
	
		}
	}
}