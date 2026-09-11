#include "event_queue.h"
#include "stm32f4xx.h"

#define EVENT_QUEUE_SIZE  20U

static SystemEvent buffer[EVENT_QUEUE_SIZE];

static volatile unsigned int head;
static volatile unsigned int tail;
static volatile unsigned int count;

void EventQueue_Init(void){
    head = 0U;
    tail = 0U;
    count = 0U;
}

int EventQueue_Push(SystemEvent event){
/*
인터럽트 상태 저장
인터럽트 잠시 금지

count가 EVENT_QUEUE_SIZE이면
    인터럽트 상태 복원
    실패 반환

buffer[head]에 event 저장
head를 다음 칸으로 이동
head가 8이면 0으로 순환
count 증가

인터럽트 상태 복원
성공 반환
*/
    uint32_t primask;

    primask = __get_PRIMASK();
    __disable_irq();

    if (count >= EVENT_QUEUE_SIZE)
    {
        __set_PRIMASK(primask);
        return 0;
    }

    buffer[head] = event;
    head = (head + 1U) % EVENT_QUEUE_SIZE;
    count++;

    __set_PRIMASK(primask);

    return 1;
}

int EventQueue_Pop(SystemEvent *event){
/*
인터럽트 상태 저장
인터럽트 잠시 금지

count가 0이면
    인터럽트 상태 복원
    실패 반환

호출자가 전달한 주소에 buffer[tail] 복사
tail을 다음 칸으로 이동
tail이 8이면 0으로 순환
count 감소

인터럽트 상태 복원
성공 반환
*/
    uint32_t primask;

    primask = __get_PRIMASK();
    __disable_irq();

    if (count == 0U)
    {
        __set_PRIMASK(primask);
        return 0;
    }

    *event = buffer[tail];
    tail = (tail + 1U) % EVENT_QUEUE_SIZE;
    count--;

    __set_PRIMASK(primask);

    return 1;
}