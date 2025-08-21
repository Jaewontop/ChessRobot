#ifndef ROBOT_ARM_IK_H
#define ROBOT_ARM_IK_H

#include <Arduino.h>
#include <Servo.h>
#include <math.h>

class RobotArmIK {
  public:
    RobotArmIK(int pin_shoulder, int pin_upper, int pin_lower, float L1, float L2);
    void begin();
    void moveTo(float x, float y, float z);

  private:
    Servo servo_shoulder;
    Servo servo_upper;
    Servo servo_lower;

    float _L1, _L2;
    int _pin_shoulder, _pin_upper, _pin_lower;

    void calculateAndMove(float x, float y, float z);
};

#endif
