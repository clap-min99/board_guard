#include "device_driver.h"
#include <stdio.h>
#include "step_motor.h"
#include "event_queue.h"


void _Invalid_ISR(void)
{
	unsigned int r = Macro_Extract_Area(SCB->ICSR, 0x1ff, 0);
	printf("\nInvalid_Exception: %d!\n", r);
	printf("Invalid_ISR: %d!\n", r - 16);
	for(;;);
}

static int temp = 0;
void EXTI15_10_IRQHandler(void)
{
    uint32_t pending;

    pending = EXTI->PR
            & ((1U << 10) | (1U << 11) | (1U << 12));

    /* 확인한 Pending을 먼저 해제 */
    EXTI->PR = pending;

    if (pending & (1U << 10))
    {
        (void)EventQueue_Push(EVT_STOP);
		Step_Motor_Stop();
    }

    if (pending & (1U << 11))
    {
        (void)EventQueue_Push(EVT_PASS);
		Step_Motor_Run();
    }

    if (pending & (1U << 12))
    {
        (void)EventQueue_Push(EVT_FAIL);
		if(temp == 0){
			Servo_Push(); 
			temp = 1;
		}else{
			Servo_Home();
			temp = 0;
		}
		
    }
}

/*
void EXTI15_10_IRQHandler(void)
{
	//printf("%ld\n", EXTI->PR);
	//printf("%ld, %ld\n", GPIOC-IDR);

	// 이벤트가 발생하면 해당 이벤트를 이벤트 큐에 집어 넣는다
    if (EXTI->PR & (1 << 10))
    {
		//printf("EXTI10\n");

        // PC10 이벤트 처리
		// 멈춰! Step_Motor_Stop();
		EventQueue_Push(EVT_STOP);

        EXTI->PR = (1 << 10);   // EXTI10 Pending clear
    }

    if (EXTI->PR & (1 << 11))
    {
		//printf("EXTI11\n");

        // PC12 이벤트 처리
		// 다시 굴러가 Step_Motor_Run();
		EventQueue_Push(EVT_PASS);

		EXTI->PR = (1 << 11);   // EXTI11 Pending clear
    }

	if (EXTI->PR & (1 << 12))
    {
		//printf("EXTI12\n");

        // PC12 이벤트 처리
		// 서보 움직여 Servo_Push(); Servo_Home();
		EventQueue_Push(EVT_FAIL);

		EXTI->PR = (1 << 12);   // EXTI12 Pending clear
    }

}
*/
