#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// I2C 통신을 사용하여 드라이버 객체를 생성합니다.
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

// --- 서보모터의 펄스 길이 설정 (중요!) ---
// 이 값들은 사용하는 서보모터의 데이터시트에 맞게 조절해야 가장 정확합니다.
// 1,500µs (마이크로초)가 보통 90도(중립)에 해당합니다.
// 0도일 때의 펄스 길이 (예: 500µs)
#define SERVO_MIN_PULSE 125 
// 180도일 때의 펄스 길이 (예: 2500µs)
#define SERVO_MAX_PULSE 525 
// 서보모터의 PWM 주파수 (보통 50Hz)
#define SERVO_FREQ 50
// 제어할 서보모터의 채널 번호
#define SERVO_CHANNEL 3 

// 기준 위치(90도)와 20도 움직일 양을 PWM 값으로 미리 계산
int base_pulse;
int move_pulse;

void setup() {
  Serial.begin(9600);
  Serial.println("Adafruit PWM Servo Driver Test");

  // 드라이버 초기화
  pwm.begin();
  // PWM 주파수 설정 (서보모터는 보통 50Hz 사용)
  pwm.setPWMFreq(SERVO_FREQ);

  // 90도(중립) 위치에 해당하는 PWM 펄스 값 계산
  base_pulse = map(60, 0, 180, SERVO_MIN_PULSE, SERVO_MAX_PULSE); // 최소 52
   
  // 110도(90도 + 20도) 위치에 해당하는 PWM 펄스 값 계산
  move_pulse = map(45, 0, 180, SERVO_MIN_PULSE, SERVO_MAX_PULSE); // 최대 46

  // 시작 시 기준 위치로 서보모터 이동
  pwm.setPWM(SERVO_CHANNEL, 0, base_pulse);
  delay(1000);
}

void loop() {
  // 1. 20도 회전 (+20도 위치로 이동)
  Serial.print(SERVO_CHANNEL);
  Serial.println("번 채널: 20도 회전");
  pwm.setPWM(SERVO_CHANNEL, 0, move_pulse);
  delay(3000); // 3초 대기

  // 2. 다시 기준 위치로 복귀
  Serial.print(SERVO_CHANNEL);
  Serial.println("번 채널: 기준 위치로 복귀");
  pwm.setPWM(SERVO_CHANNEL, 0, base_pulse);
  delay(3000); // 3초 대기
}