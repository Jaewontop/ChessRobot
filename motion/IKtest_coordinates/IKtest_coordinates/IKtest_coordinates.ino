
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include "RobotArmIK.h" // 수정된 라이브러리 호출

// --- 설정값 ---
// 서보 드라이버 채널 번호 (0부터 15까지)
#define SHOULDER_CHANNEL 0
#define UPPER_ARM_CHANNEL 1
#define LOWER_ARM_CHANNEL 2
#define GRIP_CHANNEL 3

// 링크 길이 (mm)
const float L1 = 300.0;
const float L2 = 365.0;

// 서보별 MIN/MAX 값
int servoMins[NUM_SERVOS] = {85, 85, 75, 0}; // 각 서보 최소 펄스
int servoMaxs[NUM_SERVOS] = {450, 450, 445, 0}; // 각 서보 최대 펄스

// --- 객체 생성 ---
// 1. 서보 드라이버 객체 생성
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

// 2. RobotArmIK 객체 생성 (핀 번호 대신 채널 번호와 드라이버 객체의 주소(&pwm)를 전달)
RobotArmIK robotArm(&pwm, SHOULDER_CHANNEL, UPPER_ARM_CHANNEL, LOWER_ARM_CHANNEL, GRIP_CHANNEL, L1, L2, servoMins, servoMaxs);




void setup()
{
  Serial.begin(9600);

  // 서보 드라이버 초기화
  pwm.begin();
  pwm.setOscillatorFrequency(27000000);
  pwm.setPWMFreq(50); // 서보 모터는 50Hz

  // robotArm.begin(); // 라이브러리의 begin()은 현재 비어있으므로 생략 가능
    Serial.println("체스 로봇 좌표 시스템 초기화 완료");

  robotArm.moveTo(50,50,40); // 시작 준비 자세
  delay(2000);
}

void loop() {

  if (Serial.available()) {
  float x, y, z;   // int 대신 float로 변경 (좌표 연산에 적합)

  // x 입력
  Serial.println("x좌표:");
  while (!Serial.available());             // 입력 대기
  String xcor = Serial.readStringUntil('\n');
  xcor.trim();
  x = xcor.toFloat();

  // y 입력
  Serial.println("y좌표:");
  while (!Serial.available());
  String ycor = Serial.readStringUntil('\n');
  ycor.trim();
  y = ycor.toFloat();

  // z 입력
  Serial.println("z좌표:");
  while (!Serial.available());
  String zcor = Serial.readStringUntil('\n');
  zcor.trim();
  z = zcor.toFloat();

  // 실제 로봇팔 제어 (객체 이름 주의!)
  robotArm.moveTo(x, y, z);

  delay(500);  // 입력 템포 조절 (2초 → 0.5초로 줄임)
  }
}
