#include "device_driver.h"

void jetson_init(void){
    Macro_Set_Bit(RCC->AHB1ENR, 2); 

    // PC 10, PC 12 세팅필요
    Macro_Write_Block(GPIOC->MODER, 0x3, 0x0, 20);
	Macro_Write_Block(GPIOC->PUPDR, 0x3, 0x2, 20);
    Macro_Write_Block(GPIOC->MODER, 0x3, 0x0, 24);
	Macro_Write_Block(GPIOC->PUPDR, 0x3, 0x2, 24);

    // interrupt clock on
    Macro_Set_Bit(RCC->APB2ENR, 14);

    // interrupt unmask pc 10 pc12 select
    Macro_Write_Block(SYSCFG->EXTICR[2], 0xF, 0x2, 8);
    Macro_Write_Block(SYSCFG->EXTICR[3], 0xF, 0x2, 0);

    // rising edge
    Macro_Set_Bit(EXTI->RTSR, 10); 
    Macro_Set_Bit(EXTI->RTSR, 12); 

    // pending clear
    EXTI->PR = (1<<10) | (1<<12);

    // clear
    NVIC_ClearPendingIRQ((IRQn_Type)40);
    Macro_Set_Bit(EXTI->IMR, 10);
    Macro_Set_Bit(EXTI->IMR, 12);

    NVIC_EnableIRQ((IRQn_Type)40);
}
