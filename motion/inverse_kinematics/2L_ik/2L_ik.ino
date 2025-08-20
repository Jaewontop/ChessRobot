#include <Servo.h>
#include <math.h>

// 서보 모터 객체 생성
Servo servo1; // 베이스에 연결된 서보 (첫 번째 관절)
Servo servo2; // 첫 번째 링크에 연결된 서보 (두 번째 관절)

// 로봇팔 링크 길이 (단위: cm)
const float L1 = 20.0;
const float L2 = 18.0;

void setup() {
  Serial.begin(9600);
  
  // 서보 모터 핀 연결0
  // 본인의 아두이노 핀 번호에 맞게 수정하세요.
  servo1.attach(9); 
  servo2.attach(10);
  
  Serial.println("2-Link Inverse Kinematics 예제");
  Serial.println("x,y 좌표를 콤마로 구분하여 입력하세요 (예: 15,10)");
}

/** 
목표지점 d의 x,y,z좌표 라즈베리파에서 수신(z값은 항상 동일하게 입력 받음)
--행마법 수신 방식
  --(normal,a3,a2) , (capture,b4,d5)
체스보드 = 24.6x24.7(가로x세로), 여백 가로 1.4, 세로 1.5
noraml일 땐 행마법 2개
capture일 땐 행마법 2개 사이에 데드존 좌표 입력
if로 normal과 capture 구분

x,y 좌표 참조해서 atan2() 함수로 yaw 회전량 계산
숄더 먼저 회전
x^2 + y^2 이용해서 점 d까지의 거리를 new_y에 대입
새로운 y값과 기존 z값을 이용해서 2-link inverse kinematics 계산
upper와 lower 순서대로 작동
이후 그리퍼 작동
작동했던 거를 정확히 다시 반대로 작동하여 기본 동작으로 회귀
basic posture 없이 바로 d지점에서 e지점까지 이동하는 방식
inverse kinematics로 가능하겠네 생각해보니까. 기본 위치 좌표랑 링크 길이만 입력해주면,
기본 자세에서 목표지점까지의 서보모터 각도를 계산할 거고,
서보모터 함수는 180도 중에서 하나 선택해서 입력해주면 그 각도로 움직이는 거니깐
각도를 먼저 다 계산한 후, 숄더부터 upper, lower 순으로 차례대로 구동

*/ 






void loop() {
  if (Serial.available() > 0) {
    String input = Serial.readStringUntil('\n');
    int commaIndex = input.indexOf(',');
    
    if (commaIndex > 0) {
      String xStr = input.substring(0, commaIndex);
      String yStr = input.substring(commaIndex + 1);
      
      float x = xStr.toFloat();
      float y = yStr.toFloat();

      Serial.print("목표 좌표: (");
      Serial.print(x);
      Serial.print(", ");
      Serial.print(y);
      Serial.println(")");
      
      calculateAndMove(x, y);
    } else {
      Serial.println("잘못된 입력 형식입니다. x,y 형태로 입력해주세요.");
    }
  }
}

/**
 * @brief 역기구학을 계산하고 서보 모터를 움직이는 함수
 * @param x 목표 x 좌표
 * @param y 목표 y 좌표
 */
void calculateAndMove(float x, float y) {
  // 로봇팔이 도달할 수 있는 최대 길이 확인
  float distance = sqrt(pow(x, 2) + pow(y, 2));
  if (distance > L1 + L2) {
    Serial.println("도달할 수 없는 거리입니다.");
    return;
  }


  // 각도 계산 (역기구학)
  // theta2 계산
  float cos_theta2 = (pow(x, 2) + pow(y, 2) - pow(L1, 2) - pow(L2, 2)) / (2 * L1 * L2);
  
  // acos의 입력값은 -1과 1 사이여야 함
  if (cos_theta2 < -1.0 || cos_theta2 > 1.0) {
    Serial.println("계산 오류: cos_theta2 값이 범위를 벗어났습니다.");
    return;
  }
  
  // float theta2_rad = acos(cos_theta2); // 팔꿈치가 위로 굽혀지는 경우 ('elbow up')
  float theta2_rad = -acos(cos_theta2); // 팔꿈치가 아래로 굽혀지는 경우 ('elbow down')을 원하면 이 줄의 주석을 해제

  // theta1 계산
  float k1 = L1 + L2 * cos(theta2_rad);
  float k2 = L2 * sin(theta2_rad);
  float theta1_rad = atan2(y, x) - atan2(k2, k1);

  // 라디안을 도로 변환
  float theta1_deg = theta1_rad * 180.0 / M_PI;
  float theta2_deg = theta2_rad * 180.0 / M_PI;

  Serial.print("계산된 각도 -> Servo1: ");
  Serial.print(theta1_deg);
  Serial.print("도, Servo2: ");
  Serial.print(theta2_deg);
  Serial.println("도");

  // 서보 모터 이동
  // 서보의 물리적 설치 방향 및 초기 위치에 따라 각도 값을 조절해야 할 수 있습니다.
  servo1.write(theta1_deg);
  servo2.write(theta2_deg); 
}