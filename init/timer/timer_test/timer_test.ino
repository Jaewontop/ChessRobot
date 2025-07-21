#include <TM1637Display.h>

// 버튼 핀 설정
#define BTN1 A2
#define BTN2 A3

// TM1637 핀 설정 (Player2)
#define CLK A1
#define DIO A0
TM1637Display display(CLK, DIO);

// Player1 - 직접 제어 7세그먼트
int digit_select_pin[] = {1, 2, 3, 4};     // 자릿수 선택 핀
int segment_pin[] = {5, 6, 7, 8, 9, 10, 11, 12}; // a~dp 핀
byte digits_data[10] = {
  0xFC, 0x60, 0xDA, 0xF2,
  0x66, 0xB6, 0xBE, 0xE4,
  0xFE, 0xE6
};

int time_delay = 2;
int time_p1 = 300;  // 5분
int time_p2 = 300;

bool turn_p1 = true;
unsigned long prevMillis = 0;

void setup() {
  for (int i = 0; i < 4; i++) pinMode(digit_select_pin[i], OUTPUT);
  for (int i = 0; i < 8; i++) pinMode(segment_pin[i], OUTPUT);

  pinMode(BTN1, INPUT_PULLUP);
  pinMode(BTN2, INPUT_PULLUP);

  display.setBrightness(7);
}

void show_digit(int pos, int number) {
  for (int i = 0; i < 4; i++)
    digitalWrite(digit_select_pin[i], (i + 1 == pos) ? HIGH : LOW);

  for (int i = 0; i < 8; i++) {
    byte seg = (digits_data[number] & (0x01 << i)) >> i;
    digitalWrite(segment_pin[7 - i], seg ? LOW : HIGH);
  }
}

void show_player1(int time) {
  int m = time / 60;
  int s = time % 60;
  int num = m * 100 + s;

  int d1000 = num / 1000;
  int d100 = (num % 1000) / 100;
  int d10 = (num % 100) / 10;
  int d1 = num % 10;

  show_digit(1, d1000); delay(time_delay);
  show_digit(2, d100);  delay(time_delay);
  show_digit(3, d10);   delay(time_delay);
  show_digit(4, d1);    delay(time_delay);
}

void loop() {
  unsigned long now = millis();

  // 버튼 누르면 턴 전환
  if (digitalRead(BTN1) == LOW) {
    turn_p1 = false;
    delay(200);
  }
  if (digitalRead(BTN2) == LOW) {
    turn_p1 = true;
    delay(200);
  }

  // 1초마다 타이머 감소
  if (now - prevMillis >= 1000) {
    prevMillis = now;
    if (turn_p1 && time_p1 > 0) time_p1--;
    if (!turn_p1 && time_p2 > 0) time_p2--;
  }

  // 표시 반복
  for (int i = 0; i < 5; i++) {
    show_player1(time_p1);
    display.showNumberDecEx(
      (time_p2 / 60) * 100 + (time_p2 % 60),
      0b01000000, true
    );
  }
}
