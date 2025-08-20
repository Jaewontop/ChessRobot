#include <map>
#include <string>

std::map<char, float> map_x;
std::map<char, float> map_y;

string message = ""; // 수신 받는 텍스트
bool received = false; // 텍스트 수신 여부

string start = "";
string end = "";
string moves[2]; // 필요한 움직임 수

float X[8] = {-9.45, -6.75, -4.05, -1.35, 1.35, 4.05, 6.75, 9.45};
float Y[8] = {2.95, 5.65, 8.35, 11.05, 13.75, 16.45, 19.15, 21.85};

char rows[8] = {'a','b','c','d','e','f','g','h'};
char columns[8] = {'1','2','3','4','5','6','7','8'};
// map 함수로 좌표와 행열 대응

float targetX = 0.0;  // 목표 X 좌표 (mm)
float targetY = 0.0;  // 목표 Y 좌표 (mm)
float targetZ = 0.0;  // 목표 Z 좌표 (mm)
float theta1 = 0.0;   // 베이스 회전 각도 (항상 0도)
float theta2 = 0.0;   // 어깨 관절 각도 (서보 1)
float theta3 = 0.0;   // 팔꿈치 관절 각도 (서보 2)

void setup() {
  // put your setup code here, to run once:
  map_x[char[i] = X[i]];
  map_y[char[i] = Y[i]];
}


void loop() {
  // put your main code here, to run repeatedly:
  if received{
    if (messege[0] = 'n'){
      for (int i = 0; i < 3; i++){
        
        cacluateAndMove
      }
      start = message.substring[7,9];
      end = message.substring[10];
    }
    else {
      start = message.substring[8,10];
      end = message.substring[11];
      caculateAndMove(start,end);
    }
  }
}



