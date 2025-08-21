#ifndef RobotArmIK_h
#define RobotArmIK_h

#include <Arduino.h>
#include <Servo.h>

class RobotArmIK {
  public:
    // 생성자: 그리퍼 핀까지 포함
    RobotArmIK(int pin_shoulder, int pin_upper, int pin_lower, int pin_grip,
               float L1, float L2);

    void begin();
    void moveTo(float x, float y, float z);
    void gripOpen();
    void gripClose();

  private:
    Servo servo_shoulder;
    Servo servo_upper;
    Servo servo_lower;
    Servo servo_grip;

    int pin_shoulder, pin_upper, pin_lower, pin_grip;
    float L1, L2;
};

#endif
