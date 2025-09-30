#include "RobotArmIK.h"

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include "RobotArmIK.h" // 수정된 라이브러리 호출

// --- 설정값 ---
// 서보 드라이버 채널 번호 (0부터 15까지)
#define SHOULDER_CHANNEL 0
#define UPPER_ARM_CHANNEL 1
#define LOWER_ARM_CHANNEL 2
#define GRIP_CHANNEL 3

#define CHESS_BOARD_SIZE 440.0       // 체스판 한 변 길이 (mm)
#define BOARD_MARGIN 20.0            // 체스판 한쪽 모서리 마진 (mm)
#define EFFECTIVE_BOARD_SIZE (CHESS_BOARD_SIZE - 2 * BOARD_MARGIN) // 실제 체스판 크기 (160mm)
#define SQUARE_SIZE (EFFECTIVE_BOARD_SIZE / 8.0) // 한 칸의 크기 (20mm)
#define ROBOT_ARM_OFFSET 20.0        // 로봇팔 중심과 체스판 시작점 사이의 거리 (mm)
#define DEAD_ZONE 100.0              // 잡은 말을 놓는 구역의 좌표
#define Z_HEIGHT 60.0                // 말을 잡거나 놓을 때의 Z축 높이

// 링크 길이 (mm)
const float L1 = 300.0;
const float L2 = 365.0;

// 서보별 MIN/MAX 값
int servoMins[NUM_SERVOS] = {85, 85, 75, 0}; // 각 서보 최소 펄스
int servoMaxs[NUM_SERVOS] = {450, 450, 445, 0}; // 각 서보 최대 펄스

// 각 칸의 좌표 (로봇팔 구동부 기준, 0,0이 원점, 각 칸의 중점)
float X[8] = {
    -(EFFECTIVE_BOARD_SIZE / 2) + SQUARE_SIZE / 2,
    -(EFFECTIVE_BOARD_SIZE / 2) + 3 * SQUARE_SIZE / 2,
    -(EFFECTIVE_BOARD_SIZE / 2) + 5 * SQUARE_SIZE / 2,
    -(EFFECTIVE_BOARD_SIZE / 2) + 7 * SQUARE_SIZE / 2,
    (EFFECTIVE_BOARD_SIZE / 2) - 7 * SQUARE_SIZE / 2,
    (EFFECTIVE_BOARD_SIZE / 2) - 5 * SQUARE_SIZE / 2,
    (EFFECTIVE_BOARD_SIZE / 2) - 3 * SQUARE_SIZE / 2,
    (EFFECTIVE_BOARD_SIZE / 2) - SQUARE_SIZE / 2,
};

float Y[8] = {
    ROBOT_ARM_OFFSET + BOARD_MARGIN + SQUARE_SIZE / 2,                   // 1행: 50mm (중점)
    ROBOT_ARM_OFFSET + BOARD_MARGIN + SQUARE_SIZE / 2 + SQUARE_SIZE,     // 2행: 70mm (중점)
    ROBOT_ARM_OFFSET + BOARD_MARGIN + SQUARE_SIZE / 2 + 2 * SQUARE_SIZE, // 3행: 90mm (중점)
    ROBOT_ARM_OFFSET + BOARD_MARGIN + SQUARE_SIZE / 2 + 3 * SQUARE_SIZE, // 4행: 110mm (중점)
    ROBOT_ARM_OFFSET + BOARD_MARGIN + SQUARE_SIZE / 2 + 4 * SQUARE_SIZE, // 5행: 130mm (중점)
    ROBOT_ARM_OFFSET + BOARD_MARGIN + SQUARE_SIZE / 2 + 5 * SQUARE_SIZE, // 6행: 150mm (중점)
    ROBOT_ARM_OFFSET + BOARD_MARGIN + SQUARE_SIZE / 2 + 6 * SQUARE_SIZE, // 7행: 170mm (중점)
    ROBOT_ARM_OFFSET + BOARD_MARGIN + SQUARE_SIZE / 2 + 7 * SQUARE_SIZE  // 8행: 190mm (중점)
};

// 체스 표기법 배열
char rows[8] = {'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'};
char columns[8] = {'1', '2', '3', '4', '5', '6', '7', '8'};

// 좌표 매핑 배열
float map_x[8];
float map_y[8];


// --- 객체 생성 ---
// 1. 서보 드라이버 객체 생성
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

// 2. RobotArmIK 객체 생성 (핀 번호 대신 채널 번호와 드라이버 객체의 주소(&pwm)를 전달)
RobotArmIK robotArm(&pwm, SHOULDER_CHANNEL, UPPER_ARM_CHANNEL, LOWER_ARM_CHANNEL, GRIP_CHANNEL, L1, L2, servoMins, servoMaxs);


// 체스 표기법을 좌표로 변환하는 함수
void chessToCoordinates(String chessPos, float &x, float &y)
{
  if (chessPos.length() != 2)
  {
    x = 0;
    y = 0;
    return;
  }

  char col = chessPos.charAt(0); // a, b, c, d, e, f, g, h
  char row = chessPos.charAt(1); // 1, 2, 3, 4, 5, 6, 7, 8

  // 열 인덱스 찾기 (a=0, b=1, c=2, ...)
  int colIndex = -1;
  for (int i = 0; i < 8; i++)
  {
    if (rows[i] == col) // 열이라면서 행을 적어놓은 거 실화냐 ㅋㅋㅋㅋㅋ
    {
      colIndex = i;
      break;
    }
  }

  // 행 인덱스 찾기 (1=0, 2=1, 3=2, ...)
  int rowIndex = -1;
  for (int i = 0; i < 8; i++)
  {
    if (columns[i] == row)
    {
      rowIndex = i;
      break;
    }
  }

  if (colIndex >= 0 && rowIndex >= 0)
  {
    x = X[colIndex];
    y = Y[rowIndex];
  }
  else
  {
    x = 0;
    y = 0;
  }
}


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


    String pos = Serial.readStringUntil('\n');
    pos.trim();

    if (pos.length() == 2) {
      float x, y;
      chessToCoordinates(pos, x, y);

      Serial.print("입력: "); Serial.println(pos);
      Serial.print("계산된 좌표 -> x: "); Serial.print(x);
      Serial.print(", y: "); Serial.println(y);

      // 해당 위치로 이동
      robotArm.moveTo(x, y, Z_HEIGHT);
      delay(2000);

      // 예시: 잡았다 놓기
      robotArm.gripClose(); delay(1000);
      robotArm.gripOpen();  delay(1000);
    }
  // // x 입력
  // Serial.println("x좌표:");
  // while (!Serial.available());             // 입력 대기
  // String xcor = Serial.readStringUntil('\n');
  // xcor.trim();
  // x = xcor.toFloat();

  // // y 입력
  // Serial.println("y좌표:");
  // while (!Serial.available());
  // String ycor = Serial.readStringUntil('\n');
  // ycor.trim();
  // y = ycor.toFloat();

  // // z 입력
  // Serial.println("z좌표:");
  // while (!Serial.available());
  // String zcor = Serial.readStringUntil('\n');
  // zcor.trim();
  // z = zcor.toFloat();

  // 실제 로봇팔 제어 (객체 이름 주의!)

  delay(500);  // 입력 템포 조절 (2초 → 0.5초로 줄임)
  }
}
