#include "device_driver.h"
#include "timer.h"
#include "alarm.h"

#define NOTE_C5  523U	/* 옥타브 5 도 */
#define NOTE_E5  659U	/* 옥타브 5 미 */
#define NOTE_G5  784U	/* 옥타브 5 솔 */

typedef struct
{
	unsigned short frequency_hz;	/* 음의 주파수 */
	unsigned short duration_ms;		/* 음 지속시간 */
} Alarm_Note;

/* 멜로디 배열 */
static const Alarm_Note alarm_melody[] = 
{
	/* 기상나팔 */
    /* 1. 솔 미 */
    { NOTE_G5, 540U }, { 0U, 60U },    { NOTE_E5, 340U }, { 0U, 60U },
    /* 미 미 미 */
    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_E5, 340U }, { 0U, 60U },
    /* 미 솔 미 도 */
    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_G5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_C5, 340U }, { 0U, 60U },
    /* 미 솔 미 도 미 */
    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_G5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_E5, 340U }, { 0U, 60U },
    /* 솔 미 미 */
    { NOTE_G5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_E5, 340U }, { 0U, 60U },
    /* 도 도 도 도 */
    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_C5, 540U }, { 0U, 160U },


    /* 2. 미 미 미 */
    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_E5, 340U }, { 0U, 60U },
    /* 미 솔 미 도 */
    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_G5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_C5, 340U }, { 0U, 60U },
    /* 미 솔 미 도 미 */
    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_G5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_E5, 340U }, { 0U, 60U },
    /* 솔 미 미 */
    { NOTE_G5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_E5, 340U }, { 0U, 60U },
    /* 도 도 도 도 */
    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_C5, 740U }, { 0U, 220U },


    /* 3. 솔 솔 미 */
    { NOTE_G5, 140U }, { 0U, 60U },    { NOTE_G5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },
    /* 도 미 */
    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },
    /* 도 미 도 미 */
    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },
    /* 솔 길게 */
    { NOTE_G5, 1320U }, { 0U, 220U },
    /* 4. 도 도 미 미 */
    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },
    /* 솔 솔 미 도 미 */
    { NOTE_G5, 140U }, { 0U, 60U },    { NOTE_G5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },
    /* 도 미 도 미 */
    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },    { NOTE_C5, 140U }, { 0U, 60U },    { NOTE_E5, 140U }, { 0U, 60U },
    /* 마지막 솔 */
    { NOTE_G5, 1800U }, { 0U, 500U }
};

/* 음표의 총 개수 */
#define ALARM_MELODY_LENGTH \
	(sizeof(alarm_melody) / sizeof(alarm_melody[0]))

/* 타이머 콜백에서 값이 변경되는 친구들, 인덱스 번호와 알림 상태 플래그 */
static volatile unsigned int alarm_note_index;
static volatile int alarm_enabled;

/* PWM 주파수 출력 함수 */
static void Alarm_Output_Frequency(unsigned int frequency_hz)
{
	unsigned int period;
	/* 쉼표 */
	if (frequency_hz == 0U) {
		Macro_Clear_Bit(TIM3->CCER, 0);
		return;
	}

	/* 주기 계산 */
	period = 1000000U / frequency_hz;
	/* 주기 설정 */
	TIM3->ARR = period - 1U;
	/* 사각파 만들기 */
	TIM3->CCR1 = period / 2U;
	/* 카운터 초기화 */
	TIM3->CNT = 0U;
	TIM3->EGR = 1U;
	Macro_Set_Bit(TIM3->CCER, 0);
	Macro_Set_Bit(TIM3->CR1, 0);
}

/* 현재 음표 재생 및 타이머 예약 */
static void Alarm_Play_Current_Note(void)
{
	const Alarm_Note *note = &alarm_melody[alarm_note_index];

	/* 소리키고 */
	Alarm_Output_Frequency(note->frequency_hz);
	/* 특정 시간 넣어줘서 지나면 끄기 */
	Timer2_Arm_CC1((uint32_t)note->duration_ms * 1000U);
}

/* 알람 하드웨어 초기화 */
void Alarm_Init(void)
{
	/* GPIOB 포트 클록과 TIM3 타이머 클록 */
	Macro_Set_Bit(RCC->AHB1ENR, 1);
	Macro_Set_Bit(RCC->APB1ENR, 1);
	/* 대체기능 모드 전환 후 핀 기능 설정 TIM3 CH1 */
	Macro_Write_Block(GPIOB->MODER, 0x3, 0x2, 8);   
	Macro_Write_Block(GPIOB->AFR[0], 0xf, 0x2, 16); 
	Macro_Write_Block(GPIOB->PUPDR, 0x3, 0x0, 8);

	TIM3->CR1 = 0;
	/* 분주 해서 클록을 1MHz, 한주기를 4KHz*/
	TIM3->PSC = (TIMXCLK / 1000000U) - 1U;
	TIM3->ARR = 250U - 1U;                          
	TIM3->CCR1 = 125U;
	/* PWM MODE 1, PRELOAD */
	TIM3->CCMR1 = (6U << 4) | (1U << 3);            
	TIM3->CCER = 0;
	TIM3->EGR = 1U;
	alarm_note_index = 0U;
	alarm_enabled = 0;
}

void alarm_control(int on)
{
	if (on) {
		/* 반복 호출 제어 */
		if (!alarm_enabled) {
			alarm_enabled = 1;
			alarm_note_index = 0U;
			Alarm_Play_Current_Note();
		}
	} else {
		alarm_enabled = 0;
		Timer2_Cancel_CC1();
		Macro_Clear_Bit(TIM3->CCER, 0);
		Macro_Clear_Bit(TIM3->CR1, 0);
	}
}

int Alarm_Is_Playing(void)
{
	return alarm_enabled;
}

/* 이전 음표가 끝나면 TIM2 인터럽트에 의해 콜백 함수 호출 */
void Timer2_CC1_Callback(void)
{
	/* 알람꺼지면 시마이*/
	if (!alarm_enabled) return;

	/* 루프연주 알람 끌 때까지 무한 반복 */
	alarm_note_index++;
	if (alarm_note_index >= ALARM_MELODY_LENGTH)
		alarm_note_index = 0U; 

		/* 다음 음표 주파수 시간 설정 */
	Alarm_Play_Current_Note();
}
