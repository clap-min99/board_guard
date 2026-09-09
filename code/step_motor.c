#include "device_driver.h"
#include "step_motor.h"

#define STEP_PIN    6   /* PA6 -> PUL+ */
#define DIR_PIN     7   /* PA7 -> DIR+ */
#define MOTOR_SPEED 800 /* LOW -> HIGH SPEED */


static volatile unsigned int pulse_state;

/* STEP */
static void Step_High(void){
    GPIOA->BSRR = (1U << STEP_PIN);
}

static void Step_Low(void){
    GPIOA->BSRR = (1U << (STEP_PIN + 16));
}

/* 방향 */
static void Dir_Forward(void){
    GPIOA->BSRR = (1U << DIR_PIN);
}

static void Dir_Reverse(void){
    GPIOA->BSRR = (1U << (DIR_PIN + 16));
}

void Step_Motor_Init(void){
    /* GPIOA Clock Enable */
    Macro_Set_Bit(RCC->AHB1ENR, 0);

    /* PA6(STEP), PA7(DIR) Output */
    Macro_Write_Block(GPIOA->MODER, 0xFU, 0x5U, 12);

    /* Push-Pull */
    Macro_Clear_Bit(GPIOA->OTYPER, STEP_PIN);
    Macro_Clear_Bit(GPIOA->OTYPER, DIR_PIN);

    Step_Low();
    Dir_Forward();
    /*
     * TIM4
     * 1ms마다 인터럽트 = MOTOR_SPEED 1000
     * HIGH 1ms
     * LOW  1ms
     * = 500 pulse/sec
     */
    Macro_Set_Bit(RCC->APB1ENR, 2);

    TIM4->CR1 = 0;

    TIM4->PSC = (TIMXCLK / 1000000U) - 1U;
    TIM4->ARR = MOTOR_SPEED - 1U;

    TIM4->DIER = 1U;
    TIM4->SR = 0;
    TIM4->EGR = 1U;

    NVIC_ClearPendingIRQ(TIM4_IRQn);
    NVIC_EnableIRQ(TIM4_IRQn);

    pulse_state = 0;
}


/* 정방향으로 계속 회전 */
void Step_Motor_Run(void){
    Dir_Forward();
    Step_Low();
    pulse_state = 0;

    TIM4->CNT = 0;
    TIM4->SR = 0;

    Macro_Set_Bit(TIM4->CR1, 0);
}

/* 역방향으로 계속 회전 */
void Step_Motor_Run_Reverse(void){
    Dir_Reverse();
    Step_Low();
    pulse_state = 0;

    TIM4->CNT = 0;
    TIM4->SR = 0;

    Macro_Set_Bit(TIM4->CR1, 0);
}



/* 정지 */
void Step_Motor_Stop(void){
    Macro_Clear_Bit(TIM4->CR1, 0);

    Step_Low();
    pulse_state = 0;
}


/* TIM4 interrupt */
void TIM4_IRQHandler(void){
    if ((TIM4->SR & 1U) == 0U)
        return;

    TIM4->SR &= ~1U;

    if (pulse_state == 0){
        Step_High();
        pulse_state = 1;
    }
    else{
        Step_Low();
        pulse_state = 0;
    }
}