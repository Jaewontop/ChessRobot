#ifndef ROBOTARM_IK_H
#define ROBOTARM_IK_H

#include <Adafruit_PWMServoDriver.h>

class RobotArmIK {
public:
  // 생성자
  RobotArmIK(Adafruit_PWMServoDriver* pwm,
             uint8_t channel_shoulder, uint8_t channel_upper,
             uint8_t channel_lower, uint8_t channel_grip,
             float L1, float L2);

  void begin();
  void moveTo(float x, float y, float z);
  void gripOpen();
  void gripClose();

private:
  Adafruit_PWMServoDriver* pwm; // 드라이버 객체에 대한 포인터

  // 각 서보의 채널 번호 (0~15)
  uint8_t channel_shoulder, channel_upper, channel_lower, channel_grip;

  // 로봇팔 링크 길이
  float L1, L2;

  // 각도를 펄스 길이로 변환하는 내부 함수
  int angleToPulse(float angle);
};

#endif