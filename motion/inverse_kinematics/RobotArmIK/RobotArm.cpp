#include "RobotArmIK.h"

RobotArmIK::RobotArmIK(int pin_shoulder, int pin_upper, int pin_lower, float L1, float L2) {
  _pin_shoulder = pin_shoulder;
  _pin_upper = pin_upper;
  _pin_lower = pin_lower;
  _L1 = L1;
  _L2 = L2;
}

void RobotArmIK::begin() {
  servo_shoulder.attach(_pin_shoulder);
  servo_upper.attach(_pin_upper);
  servo_lower.attach(_pin_lower);
}

void RobotArmIK::moveTo(float x, float y, float z) {
  calculateAndMove(x, y, z);
}

void RobotArmIK::calculateAndMove(float x, float y, float z) {
  float theta_shoulder_rad = atan2(y, x);

  float d = sqrt(pow(x, 2) + pow(y, 2));

  float distance = sqrt(pow(d, 2) + pow(z, 2));
  if (distance > _L1 + _L2) {
    Serial.println("도달할 수 없는 거리입니다.");
    return;
  }

  float cos_theta2 = (pow(d, 2) + pow(z, 2) - pow(_L1, 2) - pow(_L2, 2)) / (2 * _L1 * _L2);
  if (cos_theta2 < -1.0 || cos_theta2 > 1.0) {
    Serial.println("계산 오류: cos_theta2 값이 범위를 벗어났습니다.");
    return;
  }
  float theta_lower_rad = -acos(cos_theta2);

  float k1 = _L1 + _L2 * cos(theta_lower_rad);
  float k2 = _L2 * sin(theta_lower_rad);
  float theta_upper_rad = atan2(z, d) - atan2(k2, k1);

  float theta_shoulder_deg = theta_shoulder_rad * 180.0 / M_PI;
  float theta_upper_deg = theta_upper_rad * 180.0 / M_PI;
  float theta_lower_deg = theta_lower_rad * 180.0 / M_PI;

  Serial.print("계산된 각도 -> Shoulder(Yaw): ");
  Serial.print(theta_shoulder_deg);
  Serial.print("도, Upper(Pitch): ");
  Serial.print(theta_upper_deg);
  Serial.print("도, Lower(Pitch): ");
  Serial.print(theta_lower_deg);
  Serial.println("도");

  servo_shoulder.write(theta_shoulder_deg);
  servo_upper.write(theta_upper_deg);
  servo_lower.write(theta_lower_deg);
}
