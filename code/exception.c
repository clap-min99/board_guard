#include "device_driver.h"
#include <stdio.h>
#include "step_motor.h"


void _Invalid_ISR(void)
{
	unsigned int r = Macro_Extract_Area(SCB->ICSR, 0x1ff, 0);
	printf("\nInvalid_Exception: %d!\n", r);
	printf("Invalid_ISR: %d!\n", r - 16);
	for(;;);
}

void EXTI15_10_IRQHandler(void)
{
	static int servo_state = 0;
	//printf("%ld\n", EXTI->PR);
	//printf("%ld, %ld\n", GPIOC-IDR);

	// 이벤트가 발생하면 해당 이벤트를 이벤트 큐에 집어 넣는다
    if (EXTI->PR & (1 << 10))
    {
		//printf("EXTI10\n");

        // PC10 이벤트 처리
		// 멈춰!
		Step_Motor_Stop();
        EXTI->PR = (1 << 10);   // EXTI10 Pending clear
    }

    if (EXTI->PR & (1 << 11))
    {
		//printf("EXTI11\n");

        // PC12 이벤트 처리
		// 다시 굴러가
		Step_Motor_Run();

		EXTI->PR = (1 << 11);   // EXTI11 Pending clear
    }

	if (EXTI->PR & (1 << 12))
    {
		//printf("EXTI12\n");

        // PC12 이벤트 처리
		// 서보 움직여
		if(servo_state == 1){
			Servo_Push();
			servo_state = 0;
		}else{
			Servo_Home();
			servo_state = 1;
		}
		EXTI->PR = (1 << 12);   // EXTI12 Pending clear
    }

}

