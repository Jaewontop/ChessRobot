#include "RobotArmIK.h"
#include <math.h>

// 생성자
RobotArmIK::RobotArmIK(int pin_shoulder, int pin_upper, int pin_lower, int pin_grip,
                       float L1, float L2) {
  this->pin_shoulder = pin_shoulder;
  this->pin_upper = pin_upper;
  this->pin_lower = pin_lower;
  this->pin_grip = pin_grip;
  this->L1 = L1;
  this->L2 = L2;
}

void RobotArmIK::begin() {
  servo_shoulder.attach(pin_shoulder);
  servo_upper.attach(pin_upper);
  servo_lower.attach(pin_lower);
  servo_grip.attach(pin_grip);
}

void RobotArmIK::moveTo(float x, float y, float z) {
  float theta_shoulder_rad = atan2(y, x);
  float d = sqrt(pow(x, 2) + pow(y, 2));

  float distance = sqrt(pow(d, 2) + pow(z, 2));
  if (distance > L1 + L2) {
    Serial.println("도달할 수 없는 거리");
    return;
  }

  float cos_theta2 = (pow(d, 2) + pow(z, 2) - pow(L1, 2) - pow(L2, 2)) / (2 * L1 * L2);
  float theta_lower_rad = -acos(cos_theta2);

  float k1 = L1 + L2 * cos(theta_lower_rad);
  float k2 = L2 * sin(theta_lower_rad);
  float theta_upper_rad = atan2(z, d) - atan2(k2, k1);

  float theta_shoulder_deg = theta_shoulder_rad * 180.0 / M_PI;
  float theta_upper_deg = theta_upper_rad * 180.0 / M_PI;
  float theta_lower_deg = theta_lower_rad * 180.0 / M_PI;

  servo_shoulder.write(theta_shoulder_deg);
  servo_upper.write(theta_upper_deg);
  servo_lower.write(theta_lower_deg);
}

// 그리퍼 열기
void RobotArmIK::gripOpen() {
  servo_grip.write(0);     // 각도 조정 필요
  servo_lower.write(-30);  // 각도 조정 필요
}

// 그리퍼 닫기
void RobotArmIK::gripClose() {
  servo_grip.write(90);    // 각도 조정 필요
  servo_lower.write(-30);  // 각도 조정 필요
}
