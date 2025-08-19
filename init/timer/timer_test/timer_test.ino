#include <TM1637Display.h>

// 버튼 핀
#define BTN1 A2
#define BTN2 A3

// Player1용 TM1637 핀
#define CLK1 A1
#define DIO1 A0
TM1637Display display1(CLK1, DIO1);

// Player2용 TM1637 핀
#define CLK2 A5
#define DIO2 A4
TM1637Display display2(CLK2, DIO2);

int time_p1 = 600; // 10분
int time_p2 = 600;
bool turn_p1 = true;
bool timer_running = false; // 타이머 실행 상태
unsigned long prevMillis = 0;

// 시리얼 통신을 위한 변수
String inputString = "";
bool stringComplete = false;

void setup()
{
  Serial.begin(9600); // ← Serial 통신 시작

  pinMode(BTN1, INPUT_PULLUP);
  pinMode(BTN2, INPUT_PULLUP);

  display1.setBrightness(2); // 밝기 0~7
  display2.setBrightness(7);
  
  // 초기 상태 전송
  Serial.println("TIMER_READY");
}

void loop()
{
  // 시리얼 통신 처리
  serialEvent();
  
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
    
    // 시간 초과 체크
    if (time_p1 <= 0 || time_p2 <= 0) {
      timer_running = false;
      Serial.println("TIMER_EXPIRED");
    }
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

// 시리얼 통신 처리
void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    
    if (inChar == '\n') {
      stringComplete = true;
    } else {
      inputString += inChar;
    }
    
    if (stringComplete) {
      processSerialCommand(inputString);
      inputString = "";
      stringComplete = false;
    }
  }
}

// 시리얼 명령 처리
void processSerialCommand(String command) {
  command.trim();
  command.toUpperCase();
  
  Serial.print("CMD_RECEIVED: ");
  Serial.println(command);
  
  if (command == "START_TIMER") {
    startTimer();
  } else if (command == "STOP_TIMER") {
    stopTimer();
  } else if (command == "RESET_TIMER") {
    resetTimer();
  } else if (command.startsWith("SET_TIME:")) {
    // SET_TIME:600 형식으로 시간 설정
    int newTime = command.substring(9).toInt();
    if (newTime > 0) {
      setTime(newTime);
    }
  } else if (command == "GET_STATUS") {
    sendStatus();
  }
}

// 타이머 시작
void startTimer() {
  timer_running = true;
  prevMillis = millis();
  Serial.println("TIMER_STARTED");
}

// 타이머 정지
void stopTimer() {
  timer_running = false;
  Serial.println("TIMER_STOPPED");
}

// 타이머 리셋
void resetTimer() {
  time_p1 = 600; // 10분
  time_p2 = 600;
  turn_p1 = true;
  timer_running = false;
  Serial.println("TIMER_RESET");
}

// 시간 설정
void setTime(int seconds) {
  time_p1 = seconds;
  time_p2 = seconds;
  Serial.print("TIME_SET:");
  Serial.println(seconds);
}

// 상태 전송
void sendStatus() {
  Serial.print("STATUS:");
  Serial.print("P1:");
  Serial.print(time_p1);
  Serial.print(",P2:");
  Serial.print(time_p2);
  Serial.print(",TURN:");
  Serial.print(turn_p1 ? "P1" : "P2");
  Serial.print(",RUNNING:");
  Serial.println(timer_running ? "YES" : "NO");
}
