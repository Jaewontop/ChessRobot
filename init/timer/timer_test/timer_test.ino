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
bool turn_p1 = true; // true=P1 턴, false=P2 턴
bool timer_running = false; // 타이머 실행 상태
unsigned long prevMillis = 0;

void setup()
{
  Serial.begin(9600); // 시리얼 통신 시작
  delay(1000); // 시리얼 안정화 대기

  pinMode(BTN1, INPUT_PULLUP);
  pinMode(BTN2, INPUT_PULLUP);

  display1.setBrightness(2); // 밝기 0~7
  display2.setBrightness(7);
  
  // 초기 상태 전송
  Serial.println("=== CHESS TIMER START ===");
  Serial.println("TIMER_READY");
  Serial.print("INIT: P1=");
  Serial.print(time_p1);
  Serial.print("s, P2=");
  Serial.print(time_p2);
  Serial.println("s");
  
  // 바로 타이머 시작
  timer_running = true;
  prevMillis = millis();
  Serial.println("AUTO_START: 타이머가 자동으로 시작되었습니다!");
  
  // 첫 번째 데이터 전송
  Serial.print("FIRST_DATA: P1:");
  Serial.print(time_p1);
  Serial.print(",P2:");
  Serial.println(time_p2);
  
  Serial.println("SETUP_COMPLETE");
  Serial.println("========================");
}

void loop()
{
  unsigned long now = millis();

  // 타이머가 실행 중일 때만 1초마다 감소
  if (timer_running && now - prevMillis >= 1000)
  {
    prevMillis = now;
    
    // 현재 턴에 따라 시간 감소
    if (turn_p1 && time_p1 > 0) {
      time_p1--;
      Serial.print("P1 시간 감소: ");
      Serial.println(time_p1);
    }
    if (!turn_p1 && time_p2 > 0) {
      time_p2--;
      Serial.print("P2 시간 감소: ");
      Serial.println(time_p2);
    }

    // 시간 초과 체크
    if (time_p1 <= 0 || time_p2 <= 0) {
      timer_running = false;
      if (time_p1 <= 0) {
        Serial.println("GAME_OVER: P1 시간 초과!");
      } else {
        Serial.println("GAME_OVER: P2 시간 초과!");
      }
    }
  }

  // 항상 1초마다 현재 시간 정보를 라즈베리파이로 전송 (타이머 상태와 관계없이)
  static unsigned long lastDataSend = 0;
  if (now - lastDataSend >= 1000)
  {
    lastDataSend = now;
    
    // 라즈베리파이로 전송할 데이터 (간단한 형식)
    Serial.print("DATA: P1:");
    Serial.print(time_p1);
    Serial.print(",P2:");
    Serial.println(time_p2);
    
    // 시리얼 모니터용 상세 로그
    Serial.print("LOG: ");
    Serial.print(timer_running ? "RUNNING" : "STOPPED");
    Serial.print(" | P1: ");
    Serial.print(time_p1);
    Serial.print("s | P2: ");
    Serial.print(time_p2);
    Serial.print("s | Turn: ");
    Serial.println(turn_p1 ? "P1" : "P2");
    
    // 디스플레이 업데이트 (MMSS 포맷)
    int p1_display = (time_p1 / 60) * 100 + (time_p1 % 60);
    int p2_display = (time_p2 / 60) * 100 + (time_p2 % 60);
    display1.showNumberDecEx(p1_display, 0b01000000, true); // 중간 점(:) 포함
    display2.showNumberDecEx(p2_display, 0b01000000, true);
  }
  
  // 버튼 입력 처리 (턴 변경)
  if (digitalRead(BTN1) == LOW) { // P1 버튼
    if (!turn_p1) { // P2 턴이었다면 P1으로 변경
      turn_p1 = true;
      Serial.println("TURN_CHANGE: P1 턴으로 변경");
    }
    delay(200); // 디바운싱
  }
  
  if (digitalRead(BTN2) == LOW) { // P2 버튼
    if (turn_p1) { // P1 턴이었다면 P2로 변경
      turn_p1 = false;
      Serial.println("TURN_CHANGE: P2 턴으로 변경");
    }
    delay(200); // 디바운싱
  }
}
