#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <Keypad.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

const int numServos = 6;
int servoPositions[numServos] = {375, 375, 375, 375, 375, 375};
const int minPWM = 150;
const int maxPWM = 600;
const int step = 5;

const byte ROWS = 4;
const byte COLS = 4;

char keys[ROWS][COLS] = {
    {'16', '15', '14', '13'},
    {'12', '11', '10', '9'},
    {'8', '7', '6', '5'},
    {'4', '3', '2', '1'}};

byte rowPins[ROWS] = {22, 23, 24, 25};
byte colPins[COLS] = {26, 27, 28, 29};

Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

void setup()
{
  Serial.begin(9600);
  pwm.begin();
  pwm.setPWMFreq(50);
  delay(10);
  keypad.setHoldTime(100); // 0.1초만 눌러도 HOLD 상태로 인식
}

void loop()
{
  // ✔️ 최근 눌린 한 개 키만 처리 (더 빠른 반응)
  char key = keypad.getKey();
  if (key != NO_KEY)
  {
    moveServoForKey(key);
  }
  delay(20); // 너무 빠른 반복 방지
}

void moveServoForKey(char key)
{
  int servoIndex = -1;
  bool increase = false;

  // ✔️ 서보 0번
  if (key == '16') { servoIndex = 0; increase = true; }
  else if (key == '15') { servoIndex = 0; increase = false; }

  // ✔️ 서보 1번
  else if (key == '14') { servoIndex = 1; increase = true; }
  else if (key == '13') { servoIndex = 1; increase = false; }

  // ✔️ 서보 2번
  else if (key == '12') { servoIndex = 2; increase = true; }
  else if (key == '11') { servoIndex = 2; increase = false; }

  // ✔️ 서보 3번
  else if (key == '10') { servoIndex = 3; increase = true; }
  else if (key == '9') { servoIndex = 3; increase = false; }

  // ✔️ 서보 4번
  else if (key == '8') { servoIndex = 4; increase = true; }
  else if (key == '7') { servoIndex = 4; increase = false; }

  // ✔️ 서보 5번
  else if (key == '6') { servoIndex = 5; increase = true; }
  else if (key == '5') { servoIndex = 5; increase = false; }

  else return;  // 해당되지 않는 키는 무시

  // ✔️ 최종 서보 구동
  if (servoIndex >= 0 && servoIndex < numServos)
  {
    if (increase)
      servoPositions[servoIndex] = min(servoPositions[servoIndex] + step, maxPWM);
    else
      servoPositions[servoIndex] = max(servoPositions[servoIndex] - step, minPWM);

    pwm.setPWM(servoIndex, 0, servoPositions[servoIndex]);

    Serial.print("Servo ");
    Serial.print(servoIndex);
    Serial.print(increase ? " ↑ : " : " ↓ : ");
    Serial.println(servoPositions[servoIndex]);
  }
}