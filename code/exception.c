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
    }

    if (pending & (1U << 11))
    {
        (void)EventQueue_Push(EVT_PASS);
    }

    if (pending & (1U << 12))
    {
        (void)EventQueue_Push(EVT_FAIL);
    }
}