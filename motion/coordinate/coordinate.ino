#include <Arduino.h>

// 체스판 설정
#define CHESS_BOARD_SIZE 200.0                                     // 체스판 한 변 길이 (mm)
#define BOARD_MARGIN 20.0                                          // 체스판 한쪽 모서리 마진 (mm)
#define EFFECTIVE_BOARD_SIZE (CHESS_BOARD_SIZE - 2 * BOARD_MARGIN) // 실제 체스판 크기 (160mm)
#define SQUARE_SIZE (EFFECTIVE_BOARD_SIZE / 8.0)                   // 한 칸의 크기 (20mm)
#define ROBOT_ARM_OFFSET 30.0                                      // 로봇팔 부피로 인한 실제 구동부 거리 (mm)
#define DEAD_ZONE 100.0
#define Z_HEIGHT 20.0

// 각 칸의 좌표 (로봇팔 구동부 기준, 0,0이 원점, 각 칸의 중점)
float X[8] = {
    -(EFFECTIVE_BOARD_SIZE / 2) + SQUARE_SIZE / 2,     // a열: -100mm (중점)
    -(EFFECTIVE_BOARD_SIZE / 2) + 3 * SQUARE_SIZE / 2, // b열: -80mm (중점)
    -(EFFECTIVE_BOARD_SIZE / 2) + 5 * SQUARE_SIZE / 2, // c열: -60mm (중점)
    -(EFFECTIVE_BOARD_SIZE / 2) + 7 * SQUARE_SIZE / 2, // d열: -40mm (중점)
    (EFFECTIVE_BOARD_SIZE / 2) - 7 * SQUARE_SIZE / 2,  // e열: -20mm (중점)
    (EFFECTIVE_BOARD_SIZE / 2) - 5 * SQUARE_SIZE / 2,  // f열: 0mm (중점)
    (EFFECTIVE_BOARD_SIZE / 2) - 3 * SQUARE_SIZE / 2,  // g열: 20mm (중점)
    (EFFECTIVE_BOARD_SIZE / 2) - SQUARE_SIZE / 2,      // h열: 40mm (중점)
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

// 체스 기물 이동 함수
void calculateAndMove(float x, float y, float z)
{
  // TODO: 실제 3L_ik.ino에 있는 함수와 연동하기
  Serial.print("이동: X=");
  Serial.print(x);
  Serial.print(", Y=");
  Serial.print(y);
  Serial.print(", Z=");
  Serial.println(z);
}


// 그리퍼 제어 함수들
void gripperClose()
{
  // TODO: 그리퍼 닫기 함수 만들기
  Serial.println("그리퍼 닫기");
}

void gripperOpen()
{
  // TODO: 그리퍼 열기 함수 만들기
  Serial.println("그리퍼 열기");
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
    if (rows[i] == col)
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

  // READY 상태로 초기화
  calculateAndMove(0, 0, 60);
}

void loop()
{
  // 라즈베리파이로부터 메시지 수신
  message = getMessage();

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
  calculateAndMove(x, y, Z_HEIGHT);

  // 2. 그리퍼로 잡기
  gripperClose();

  // 3. DEAD_ZONE으로 이동
  calculateAndMove(DEAD_ZONE, DEAD_ZONE, DEAD_ZONE);

  // 4. 그리퍼 열기
  gripperOpen();

  // 5. READY 상태로 돌아가기 (0,0,0)
  calculateAndMove(0, 0, 0);

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
  calculateAndMove(startX, startY, Z_HEIGHT);

  // 2. 그리퍼로 잡기
  gripperClose();

  // 3. DEAD_ZONE으로 이동
  calculateAndMove(DEAD_ZONE, DEAD_ZONE, DEAD_ZONE);

  // 4. 끝 위치로 이동
  calculateAndMove(endX, endY, Z_HEIGHT);

  // 5. 그리퍼 열기
  gripperOpen();

  // 6. READY 상태로 돌아가기 (0,0,0)
  calculateAndMove(0, 0, 0);

  Serial.println("이동 완료!");

  // 라즈베리파이로 완료 신호 전송
  Serial.println("MOVE_COMPLETE");
}