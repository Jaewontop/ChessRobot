#include <RobotArmIK.h>

RobotArmIK robotArm(9, 10, 11, 12, 200.0, 180.0);  // 12번 핀: 그리퍼

void setup() {
  Serial.begin(9600);
  robotArm.begin();
}

void loop() {
  robotArm.moveTo(150, 50, 100);
  delay(2000);

  robotArm.gripOpen();   // 그리퍼 열기
  delay(1000);

  robotArm.gripClose();  // 그리퍼 닫기
  delay(2000);
}
