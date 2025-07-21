#include <Servo.h>

Servo myServo;

void setup() {
  myServo.attach(9);     // 서보 모터는 PWM 가능한 디지털 핀에 연결 (예: D9)
  Serial.begin(9600);
}

void loop() {
  int potValue = analogRead(A0);              // A0 핀에서 0~1023 값 읽음
  int angle = map(potValue, 0, 1023, 150, 600);  // 서보용 0~180도로 변환

  myServo.write(angle);                       // 서보 각도 설정
  Serial.print("Potentiometer: ");
  Serial.print(potValue);
  Serial.print(" → Servo angle: ");
  Serial.println(angle);

  delay(15);  // 서보가 움직일 시간 확보
}
