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
const float L1 = 200.0;
const float L2 = 180.0;

// 체스판 설정
#define CHESS_BOARD_SIZE 200.0       // 체스판 한 변 길이 (mm)
#define BOARD_MARGIN 20.0            // 체스판 한쪽 모서리 마진 (mm)
#define EFFECTIVE_BOARD_SIZE (CHESS_BOARD_SIZE - 2 * BOARD_MARGIN) // 실제 체스판 크기 (160mm)
#define SQUARE_SIZE (EFFECTIVE_BOARD_SIZE / 8.0) // 한 칸의 크기 (20mm)
#define ROBOT_ARM_OFFSET 30.0        // 로봇팔 중심과 체스판 시작점 사이의 거리 (mm)
#define DEAD_ZONE 100.0              // 잡은 말을 놓는 구역의 좌표
#define Z_HEIGHT 20.0                // 말을 잡거나 놓을 때의 Z축 높이


// --- 객체 생성 ---
// 1. 서보 드라이버 객체 생성
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

// 2. RobotArmIK 객체 생성 (핀 번호 대신 채널 번호와 드라이버 객체의 주소(&pwm)를 전달)
RobotArmIK robotArm(&pwm, SHOULDER_CHANNEL, UPPER_ARM_CHANNEL, LOWER_ARM_CHANNEL, GRIP_CHANNEL, L1, L2);


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

bool received = false;

String getMessage()
{
  // TODO: 실제로 라즈베리파이에서 값 받아올 수 있게 수정하기
  String receivedMessage = "";

  if (Serial.available() > 0)
  {
    receivedMessage = Serial.readStringUntil('\n');
    receivedMessage.trim(); // 앞뒤 공백 제거

    if (receivedMessage.length() > 0)
    {
      Serial.print("수신된 메시지: ");
      Serial.println(receivedMessage);
      return receivedMessage;
    }
  }

  return ""; // 메시지가 없으면 빈 문자열 반환
}


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

  // 좌표 매핑 초기화
  for (int i = 0; i < 8; i++)
  {
    map_x[i] = X[i];
    map_y[i] = Y[i];
  }

  Serial.println("체스 로봇 좌표 시스템 초기화 완료");
  Serial.print("체스판 크기: ");
  Serial.print(CHESS_BOARD_SIZE);
  Serial.println("mm");
  Serial.print("실제 체스판 크기: ");
  Serial.print(EFFECTIVE_BOARD_SIZE);
  Serial.println("mm");
  Serial.print("한 칸 크기: ");
  Serial.print(SQUARE_SIZE);
  Serial.println("mm");
  Serial.print("로봇팔 오프셋: ");
  Serial.print(ROBOT_ARM_OFFSET);
  Serial.println("mm");
  Serial.print("데드존: ");
  Serial.print(DEAD_ZONE);
  Serial.println("mm");
  
  // 시작 준비 자세로 이동
  robotArm.moveTo(0, 0, 60); // 예시: x=150, y=0, z=100
  delay(2000);

}

void loop()
{
  // 라즈베리파이로부터 메시지 수신
  String message = getMessage();

  if (message.length() > 0)
  {
    received = true;

    // 메시지 타입 확인 및 처리
    if (message.length() >= 4)
    {
      if (message.substring(2).equals("cap"))
      {
        // 캡처 타입: c7cap -> c7 위치의 기물을 DEAD_ZONE으로 이동
        String capturePos = message.substring(0, 2);
        processCapture(capturePos);
      }
      else
      {
        // 일반 이동 타입: c5c7 -> c5에서 c7로 이동
        processChessMove(message);
      }
    }

    received = false; // 처리 완료
  }

  turnOver(); // 차례 종료
}

// 캡처 처리 함수
void processCapture(String capturePos)
{
  float x, y;

  // 캡처할 위치 좌표 계산
  chessToCoordinates(capturePos, x, y);

  Serial.print("캡처: ");
  Serial.println(capturePos);
  Serial.print("좌표: (");
  Serial.print(x);
  Serial.print(", ");
  Serial.print(y);
  Serial.println(")");

  // 1. 캡처할 위치로 이동 (Z=20으로 고정)
  robotArm.moveTo(x, y, Z_HEIGHT);
  delay(2000);

  // 2. 그리퍼로 잡기
  robotArm.gripClose();
  delay(2000);

  // 3. DEAD_ZONE으로 이동
  robotArm.moveTo(DEAD_ZONE, DEAD_ZONE, DEAD_ZONE);

  // 4. 그리퍼 열기
  robotArm.gripOpen();
  delay(2000);


  // 라즈베리파이로 완료 신호 전송
  Serial.println("CAPTURE_COMPLETE");
}

// 체스 기물 이동 처리 함수
void processChessMove(String move)
{
  if (move.length() < 4)
  {
    Serial.println("잘못된 이동 명령");
    return;
  }

  String startPos = move.substring(0, 2); // 시작 위치 (예: c7)
  String endPos = move.substring(2, 4);   // 끝 위치 (예: c5)

  float startX, startY, endX, endY;

  // 시작 위치 좌표 계산
  chessToCoordinates(startPos, startX, startY);

  // 끝 위치 좌표 계산
  chessToCoordinates(endPos, endX, endY);

  Serial.print("이동: ");
  Serial.print(startPos);
  Serial.print(" -> ");
  Serial.println(endPos);
  Serial.print("좌표: (");
  Serial.print(startX);
  Serial.print(", ");
  Serial.print(startY);
  Serial.print(") -> (");
  Serial.print(endX);
  Serial.print(", ");
  Serial.print(endY);
  Serial.println(")");

  // 1. 시작 위치로 이동 (Z=20으로 고정)
  robotArm.moveTo(startX, startY, Z_HEIGHT);
  delay(2000);

  // 2. 그리퍼로 잡기
  robotArm.gripClose();
  delay(2000);

  // 3. DEAD_ZONE으로 이동
  robotArm.moveTo(DEAD_ZONE, DEAD_ZONE, DEAD_ZONE);
  delay(2000);

  // 4. 끝 위치로 이동
  robotArm.moveTo(endX, endY, Z_HEIGHT);
  delay(2000);

  // 5. 그리퍼 열기
  robotArm.gripOpen();
  delay(2000);


  Serial.println("이동 완료!");

  // 라즈베리파이로 완료 신호 전송
  Serial.println("MOVE_COMPLETE");
}

// 차례 종료하는 함수
void turnOver() {
  
  robotArm.moveTo(100,100,20); // 타이머 위치 임의 지정
  delay(2000);
}