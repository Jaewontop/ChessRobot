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
    {'A', 'B', 'C', 'D'},
    {'E', 'F', 'G', 'H'},
    {'I', 'J', 'K', 'L'},
    {'M', 'N', 'O', 'P'}};

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
  char key = keypad.getKey();
  if (key != NO_KEY)
  {
    Serial.println(key);
    //moveServoForKey(key);
  }
  delay(20);
}

void moveServoForKey(char key)
{
  int servoIndex = -1;
  bool increase = false;

   switch (key) {
    case 'A': servoIndex = 0; increase = true; break;
    case 'B': servoIndex = 0; increase = false; break;

    case 'C': servoIndex = 1; increase = true; break;
    case 'D': servoIndex = 1; increase = false; break;

    case 'E': servoIndex = 2; increase = true; break;
    case 'F': servoIndex = 2; increase = false; break;

    case 'G': servoIndex = 3; increase = true; break;
    case 'H': servoIndex = 3; increase = false; break;

    case 'I': servoIndex = 4; increase = true; break;
    case 'J': servoIndex = 4; increase = false; break;

    case 'K': servoIndex = 5; increase = true; break;
    case 'L': servoIndex = 5; increase = false; break;

    default: return;
  }

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
