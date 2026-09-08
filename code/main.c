#if 0

#include "device_driver.h"
#include "timer.h"
#include <stdio.h>

static void Sys_Init(int baud)
{
	SCB->CPACR |= (0x3 << 10*2)|(0x3 << 11*2);
	Clock_Init();
	Uart2_Init(baud);
	setvbuf(stdout, NULL, _IONBF, 0);
	Sensor_Control_Init();
}

void Main(void){
    volatile unsigned int i;
	int test = 1;
    Sys_Init(115200);
    printf("\n=== individual device test ===\n");
	for (i = 0; i < SYSCLK/10U; i++){ __NOP(); }
	alarm_control(1);
    for (;;){
		for (i = 0; i < SYSCLK/10U; i++){ __NOP(); }
		led_control(test);
		step_motor_control(100);
		if(test == 1){
			test = 0;
		}else{ test = 1;}
    }
}

#else

#include "device_driver.h"
#include "timer.h"
#include <stdio.h>

static void Sys_Init(int baud)
{
	SCB->CPACR |= (0x3 << 10*2)|(0x3 << 11*2);
	Clock_Init();
	Uart2_Init(baud);
	setvbuf(stdout, NULL, _IONBF, 0);
	Sensor_Control_Init();
}

// 상태를 3개 가져야한다.

void Main(void){
	Sys_Init(115200);
	volatile unsigned int i;
	for(;;){
/*
RUNNING
   │
   │ PC12
   ▼
INSPECTING
   │
   ├── PC10 → FAIL 처리
   │
   └── PC11 → 다시 RUNNING
*/

	}
}

#endif

#if 0

#include "device_driver.h"
#include "timer.h"
#include <stdio.h>

static void Sys_Init(int baud)
{
	SCB->CPACR |= (0x3 << 10*2)|(0x3 << 11*2);
	Clock_Init();
	Uart2_Init(baud);
	setvbuf(stdout, NULL, _IONBF, 0);
	Sensor_Control_Init();
}

// 상태를 3개 가져야한다.

void Main(void){
	Sys_Init(115200);
	volatile unsigned int i;
	for(;;){
		LED_GREEN_ON();
		LED_RED_ON();

		for (i = 0; i < SYSCLK/10U; i++){ __NOP(); }

		LED_GREEN_Off();
		LED_RED_Off();

		for (i = 0; i < SYSCLK/10U; i++){ __NOP(); }
	}
}


#else

#endif


#if 0


#include "device_driver.h"
#include "timer.h"
#include <stdio.h>

static void Sys_Init(int baud)
{
	SCB->CPACR |= (0x3 << 10*2)|(0x3 << 11*2);
	Clock_Init();
	Uart2_Init(baud);
	setvbuf(stdout, NULL, _IONBF, 0);
	Sensor_Control_Init();
}

// 상태를 3개 가져야한다.

void Main(void){
	Sys_Init(115200);
	volatile unsigned int i;
	for(;;){
	}
}


#else

#endif