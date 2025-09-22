#include "RobotArmIK.h"
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

#define NUM_SERVOS 4  // 사용하는 모터 개수 (어깨, 상박, 하박, 그리퍼)

// 생성자: 드라이버 객체 포인터와 각 서보의 '채널 번호'와 서보별 min/max 값을 입력받습니다.
RobotArmIK::RobotArmIK(Adafruit_PWMServoDriver* pwm,
                     uint8_t channel_shoulder, uint8_t channel_upper,
                     uint8_t channel_lower, uint8_t channel_grip,
                     float L1, float L2,
                     int servoMins[NUM_SERVOS], int servoMaxs[NUM_SERVOS]) {
  this->pwm = pwm;
  this->channel_shoulder = channel_shoulder;
  this->channel_upper = channel_upper;
  this->channel_lower = channel_lower;
  this->channel_grip = channel_grip;
  this->L1 = L1;
  this->L2 = L2;

   // [추가] 배열 복사
  for (int i = 0; i < NUM_SERVOS; i++) {
    this->servoMins[i] = servoMins[i];
    this->servoMaxs[i] = servoMaxs[i];
  }
}

  

// 이 클래스에서는 특별히 할 일이 없으므로 비워둡니다.
// 드라이버 초기화는 메인 .ino 파일에서 수행합니다.
void RobotArmIK::begin() {
  // pwm->begin(); // 드라이버 시작 코드는 setup()에서 한 번만 호출하는 것이 좋습니다.
}



// 각도를 펄스로 변환 (채널별 개별 min/max 적용)
int RobotArmIK::angleToPulse(uint8_t channel, float angle) {
  int idx = 0;

  // 채널 번호에 따라 배열 인덱스 결정
  if (channel == channel_shoulder) idx = 0;
  else if (channel == channel_upper) idx = 1;
  else if (channel == channel_lower) idx = 2;
  else if (channel == channel_grip) idx = 3;

  return map(angle, 0, 180, servoMins[idx], servoMaxs[idx]);
}

void RobotArmIK::moveTo(float x, float y, float z) {
  float theta_shoulder_rad = atan2(y, x);
  float d = sqrt(pow(x, 2) + pow(y, 2));

  float distance = sqrt(pow(d, 2) + pow(z, 2));
  if (distance > L1 + L2) {
    Serial.println("도달할 수 없는 거리");
    return;
  }

  float cos_theta2 = (pow(L1, 2) - pow(L2, 2) - pow(d, 2) + pow(z, 2)) / (2 * L1 * L2);
  float theta_lower_rad = acos(cos_theta2);

  float k1 = L1 + L2 * cos(theta_lower_rad);
  float k2 = L2 * sin(theta_lower_rad);
  float theta_upper_rad = M_PI - atan2(z, d) - atan2(k2, k1); // theta 값 연산 실수 수정

  float theta_shoulder_deg = theta_shoulder_rad * 180.0 / M_PI;
  float theta_upper_deg = theta_upper_rad * 180.0 / M_PI;
  float theta_lower_deg = theta_lower_rad * 180.0 / M_PI;

  // [중요] 계산된 각도를 실제 서보 모터의 0~180도 범위로 변환
  // 이 부분은 실제 로봇팔의 조립 상태에 맞춰 수정이 필요합니다.
  float shoulder_angle = constrain(theta_shoulder_deg, 0, 180);
  float upper_angle    = constrain(theta_upper_deg, 0, 180);
  float lower_angle    = constrain(theta_lower_deg, 0, 180);

  // [수정] 채널 포함해서 호출
  pwm->setPWM(channel_shoulder, 0, angleToPulse(channel_shoulder, shoulder_angle));
  pwm->setPWM(channel_upper,    0, angleToPulse(channel_upper, upper_angle));
  pwm->setPWM(channel_lower,    0, angleToPulse(channel_lower, lower_angle));
}

// 그리퍼 열기
void RobotArmIK::gripOpen() {
  pwm->setPWM(channel_grip,  0, angleToPulse(channel_grip, 0));   // 0도에 해당하는 펄스 값
  pwm->setPWM(channel_lower, 0, angleToPulse(channel_grip, 0)); // 다시 올라옴
}

// 그리퍼 닫기
void RobotArmIK::gripClose() {
  pwm->setPWM(channel_grip,  0, angleToPulse(channel_grip, 90));  // 90도에 해당하는 펄스 값
  pwm->setPWM(channel_lower, 0, angleToPulse(channel_grip, 0));  // 다시 올라옴
}
