#include "device_driver.h"
#include "timer.h"
#include "servo.h"
#include "event_queue.h"

/* 연속회전 MG90S 전용. PWM 폭=속도/방향, 시간=회전량(각도 보장 없음). */
#define SERVO_PERIOD_US       20000U
#define SERVO_STOP_PULSE_US     1500U /* 현물의 중립값으로 조정 */
#define SERVO_RUN_PULSE_US      2000U /* 반대 방향은 2000us 부근 */
#define SERVO_RUN_MS           720U /* 실측 후 조정 660 또는 680 이나을듯. */
#define SERVO_STOP_SETTLE_MS     200U
#define SERVO_RUN_PERIODS ((SERVO_RUN_MS * 1000U + SERVO_PERIOD_US - 1U) / SERVO_PERIOD_US)
#define SERVO_STOP_PERIODS ((SERVO_STOP_SETTLE_MS * 1000U + SERVO_PERIOD_US - 1U) / SERVO_PERIOD_US)

enum { SERVO_IDLE, SERVO_ROTATING, SERVO_STOPPING };
static volatile unsigned int servo_mode;
static volatile unsigned int servo_high;
static volatile unsigned int servo_count;
static volatile unsigned int servo_pulse;

static void Servo_Start(unsigned int mode, unsigned int pulse)
{
    uint32_t primask = __get_PRIMASK();
    __disable_irq();
    Timer2_Cancel_CC2();
    servo_mode = mode;
    servo_pulse = pulse;
    servo_count = 0U;
    servo_high = 1U;
    GPIOB->BSRR = 1U << 5;
    Timer2_Arm_CC2(servo_pulse);
    __set_PRIMASK(primask);
}

void Servo_Init(void)
{
    Macro_Set_Bit(RCC->AHB1ENR, 1);
    Macro_Write_Block(GPIOB->MODER, 0x3, 0x1, 10);
    Macro_Clear_Bit(GPIOB->OTYPER, 5);
    GPIOB->BSRR = 1U << (5 + 16);
    /* Timer2はSensor_Control_Initで先に初期化済み。중립 PWM을 계속 출력한다. */
    Servo_Start(SERVO_IDLE, SERVO_STOP_PULSE_US);
}

void Servo_Push(void)
{
    Servo_Start(SERVO_ROTATING, SERVO_RUN_PULSE_US);
}

void Servo_Home(void)
{
    /* 기존 API 이름 유지. 연속회전형이므로 원점 복귀가 아니라 정지. */
    Servo_Start(SERVO_STOPPING, SERVO_STOP_PULSE_US);
}

void Timer2_CC2_Callback(void)
{
    if (servo_high) {
        GPIOB->BSRR = 1U << (5 + 16);
        servo_high = 0U;
        Timer2_Arm_CC2(SERVO_PERIOD_US - servo_pulse);
        return;
    }

    if (servo_mode == SERVO_ROTATING) {
        if (++servo_count >= SERVO_RUN_PERIODS) {
            servo_pulse = SERVO_STOP_PULSE_US;
            servo_count = 0U;
            servo_mode = SERVO_STOPPING;
        }
    } else if (servo_mode == SERVO_STOPPING) {
        if (++servo_count >= SERVO_STOP_PERIODS) {
            servo_mode = SERVO_IDLE;
            (void)EventQueue_Push(EVT_SERVO_DONE);
        }
    }

    /* 완료 후에도 중립 PWM 유지. 완료 이벤트는 한 동작당 한 번. */
    servo_high = 1U;
    GPIOB->BSRR = 1U << 5;
    Timer2_Arm_CC2(servo_pulse);
}
