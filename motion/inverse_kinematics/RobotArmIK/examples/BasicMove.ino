#include <RobotArmIK.h>

// 링크 길이 (mm)
const float L1 = 200.0;
const float L2 = 180.0;

// 핀 번호 (아두이노 핀 번호에 맞게 수정)
RobotArmIK robotArm(9, 10, 11, L1, L2);

void setup() {
  Serial.begin(9600);
  robotArm.begin();
}

void loop() {
  robotArm.moveTo(150, 50, 100);  
  delay(2000);
  robotArm.moveTo(200, 0, 50);
  delay(2000);
}
