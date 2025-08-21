#include <Servo.h>
#include <math.h>

// 서보 모터 객체 생성
Servo servo1; // 베이스에 연결된 서보 (첫 번째 관절)
Servo servo2; // 첫 번째 링크에 연결된 서보 (두 번째 관절)

// 로봇팔 링크 길이 (단위: mm)
const float L1 = 200.0;
const float L2 = 180.0;

void setup() {
  Serial.begin(9600);
  
  // 서보 모터 핀 연결0
  // 본인의 아두이노 핀 번호에 맞게 수정하세요.
  servo1.attach(9); 
  servo2.attach(10);

}




void loop() {
  calculateAndMove(tartgetX, targetY, targetZ);
}

/**
 * @brief 역기구학을 계산하고 서보 모터를 움직이는 함수
 * @param x 목표 x 좌표
 * @param y 목표 y 좌표
 */
void calculateAndMove(float x, float y, float z) {
  // 1. Shoulder yaw 계산
  float theta_shoulder_rad = atan2(y, x);

  // 2. 수평 거리 d 계산
  float d = sqrt(pow(x, 2) + pow(y, 2));

  // 3. 2링크 IK 계산 (Upper + Lower)
  float distance = sqrt(pow(d, 2) + pow(z, 2));
  if (distance > L1 + L2) {
    Serial.println("도달할 수 없는 거리입니다.");
    return;
  }

  // elbow angle (theta_lower)
  float cos_theta2 = (pow(d, 2) + pow(z, 2) - pow(L1, 2) - pow(L2, 2)) / (2 * L1 * L2);
  if (cos_theta2 < -1.0 || cos_theta2 > 1.0) {
    Serial.println("계산 오류: cos_theta2 값이 범위를 벗어났습니다.");
    return;
  }
  float theta_lower_rad = -acos(cos_theta2); // elbow down

  // shoulder pitch (theta_upper)
  float k1 = L1 + L2 * cos(theta_lower_rad);
  float k2 = L2 * sin(theta_lower_rad);
  float theta_upper_rad = atan2(z, d) - atan2(k2, k1);

  // 라디안 -> 도
  float theta_shoulder_deg = theta_shoulder_rad * 180.0 / M_PI;
  float theta_upper_deg = theta_upper_rad * 180.0 / M_PI;
  float theta_lower_deg = theta_lower_rad * 180.0 / M_PI;

  // 결과 출력
  Serial.print("계산된 각도 -> Shoulder(Yaw): ");
  Serial.print(theta_shoulder_deg);
  Serial.print("도, Upper(Pitch): ");
  Serial.print(theta_upper_deg);
  Serial.print("도, Lower(Pitch): ");
  Serial.print(theta_lower_deg);
  Serial.println("도");

  // 서보 모터 동작
  servo_shoulder.write(theta_shoulder_deg);
  servo_upper.write(theta_upper_deg);
  servo_lower.write(theta_lower_deg);
}
