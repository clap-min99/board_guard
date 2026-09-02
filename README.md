# 개발계획

## 개발기간
08.31 ~ 9.18

## 버전
2트랙으로 진행 각 모델 별 반환해주는 값이 조금 다르다. 해당 브랜치 참조
욜로 모델
오류 확인 모델


## 담당구역

```프로그램
     [카메라]
        |
        v
  [YOLO 담당 영역]
        |
        v
   PCB 불량 판정
        |
        v
class, confidence, b_box, 좌표 .....
현재 dectection 결과 저장
        |
        v
      [구현]
PCB 존재 판단
1초 검사
정상 조건 비교
검사 상태 관리 및 결과 확정
상태 결정, 검사 결과 데이터 생성 및 저장
      [구현]
        |
        v
    [UI 담당 영역]
```

## 인터페이스

### YOLO -> ME  
     함수 호출
     get_detections() 
     return type : tuple
     순서 : class,  detail, object_box, bounding_box
     class는 0과 1로 들어온다.

### ME -> UI

    UI 담당자 사용 함수
    get_inspection_result()
    반환 값 튜플
    {
          state,
          result,
          message,
          details,
          bounding_box,
          check_number
    }

반환값
| 항목 | 의미 |
| --- | --- |
| state | 현재 검사 상태 |
| result | 최종 정상 / 불량 결과 |
| message | 넘겨줄 메시지 |
| details | 불량 원인 |
| o_box | 측정PCB박스 |
| b_box | 비정상 검출 부위 |
| check_number | 총 측정한 개수 |

| 목록 | 정상 | 비정상 | 미감지 | 검사중 |
| --- | --- | --- | --- | --- |
| state | PASS | FAIL | MISSING | INSPECTING |
| result | NORMAL | DEEFECT | NULL | NULL |
| message | PASS | FAIL | MISSING | INSPECTING |
| details | NULL | FAIL | NULL | NULL |
| object_box | o_box | o_box | NULL | o_box |
| bounding_box | b_box | b_box | NULL | b_box |
| check_number | check_num | check_num | check_num | check_num |

## 구조

```
프로그램 시작
    |
    v
[대기상태]
    |
    v
PCB 발견
    |
    v
[1초 검사]
    |
    v
결과 확정
    |
    v
[결과 제출]
    |
    v
PCB 존재시 결과 유지
    OR
PCB 제거시 대기상태 전환

```
## 구현 방식

### 검사 상태 관리 방식

### 상태 결정 방식

### 결과 확정 방식

### 결과 데이터 생성

