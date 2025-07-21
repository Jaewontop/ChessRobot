#include <TM1637Display.h>

// Player1 핀 연결
int digit_select_pin[] = {1, 2, 3, 4};     // digit 선택
int segment_pin[] = {5, 6, 7, 8, 9, 10, 11, 12}; // a ~ dp
byte digits_data[10] = {0xFC, 0x60, 0xDA, 0xF2,
                        0x66, 0xB6, 0xBE, 0xE4, 0xFE, 0xE6};
int time_delay = 2;

// Player2 핀 (TM1637)
#define CLK A1
#define DIO A0
TM1637Display display(CLK, DIO);

void setup() {
  // Player1 핀 설정
  for (int i = 0; i < 4; i++) pinMode(digit_select_pin[i], OUTPUT);
  for (int i = 0; i < 8; i++) pinMode(segment_pin[i], OUTPUT);

  // Player2 디스플레이 밝기 설정
  display.setBrightness(1); // 0~7
}

void show_digit(int pos, int number) {
  for (int i = 0; i < 4; i++) {
    if (i + 1 == pos)
      digitalWrite(digit_select_pin[i], HIGH);
    else
      digitalWrite(digit_select_pin[i], LOW);
  }
  for (int i = 0; i < 8; i++) {
    byte segment_data = (digits_data[number] & (0x01 << i)) >> i;
    digitalWrite(segment_pin[7 - i], segment_data ? LOW : HIGH);
  }
}

void loop() {
  for (int i = 0; i < 10000; i++) {
    int d1000 = i / 1000;
    int d100 = (i % 1000) / 100;
    int d10 = (i % 100) / 10;
    int d1 = i % 10;

    for (int j = 0; j < 10; j++) {
      // Player1 표시
      show_digit(1, d1000); delay(time_delay);
      show_digit(2, d100);  delay(time_delay);
      show_digit(3, d10);   delay(time_delay);
      show_digit(4, d1);    delay(time_delay);

      // Player2 표시
      display.showNumberDec(i, true); // TM1637은 알아서 표시됨
    }
  }
}
