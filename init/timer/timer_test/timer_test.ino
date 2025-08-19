#include <TM1637Display.h>

// 버튼 핀
#define BTN1 A2
#define BTN2 A3

// Player1용 TM1637 핀
#define CLK1 A1
#define DIO1 A0
TM1637Display display1(CLK1, DIO1);

// Player2용 TM1637 
#define CLK2 A5
#define DIO2 A4
TM1637Display display2(CLK2, DIO2);

int time_p1 = 600; // 10분
int time_p2 = 600;
bool turn_p1 = false; // 시작하자마자 P2(흰색)부터 감소
bool timer_running = true; // 부팅 즉시 실행
unsigned long prevMillis = 0;

// 시리얼 명령 처리 제거 (간소화 동작)

void setup()
{
  Serial.begin(9600); // ← Serial 통신 시작

  pinMode(BTN1, INPUT_PULLUP);
  pinMode(BTN2, INPUT_PULLUP);

  display1.setBrightness(2); // 밝기 0~7
  display2.setBrightness(7);
  
  // 초기 설정: P2 차례로 시작
  turn_p1 = false;
  timer_running = true;
  prevMillis = millis();
}

void loop()
{
  unsigned long now = millis();

  // 타이머가 실행 중일 때만 1초마다 감소
  if (timer_running && now - prevMillis >= 1000)
  {
    prevMillis = now;
    if (turn_p1 && time_p1 > 0)
      time_p1--;
    if (!turn_p1 && time_p2 > 0)
      time_p2--;

    // 1초마다 현재 시간 정보를 라즈베리파이로 전송
    Serial.print("P1:");
    Serial.print(time_p1);
    Serial.print(",P2:");
    Serial.println(time_p2);
    // 시간이 0에 도달해도 송신은 계속, 감소만 멈춤
  }

  // 버튼 눌러서 턴 전환
  if (digitalRead(BTN1) == LOW)
  {
    turn_p1 = false;
    delay(200); // 디바운싱
  }
  if (digitalRead(BTN2) == LOW)
  {
    turn_p1 = true;
    delay(200);
  }

  // MMSS 포맷으로 변환 (예: 2분 5초 → 0205)
  int p1_display = (time_p1 / 60) * 100 + (time_p1 % 60);
  int p2_display = (time_p2 / 60) * 100 + (time_p2 % 60);

  // 표시 (중간 점(:) 포함)
  display1.showNumberDecEx(p1_display, 0b01000000, true);
  display2.showNumberDecEx(p2_display, 0b01000000, true);
}

// 명령/상태 관련 함수 제거로 코드 간소화 완료
