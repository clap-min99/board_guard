# 개발계획

## 개발기간
08.31 ~ 9.18

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
        |
        v
      [구현]
검사 상태 관리, 결과 확정, 
상태 결정, 검사 결과 데이터 생성
      [구현]
        |
        v
    [UI 담당 영역]
```

## 인터페이스

### YOLO -> ME  
    result = FALE  
    reason = FALE 사유(pin_broken or register missing, capasiter missing.....)  
    bounding box = 받기  

### ME -> UI
    함수로해서 리턴할 수 있게 넘겨주기  
    리턴 값은 리스트로 정상 불량, 불량 사유, 박스, 체크 개수
    UI담당자에게 

## 구현 알고리즘

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

