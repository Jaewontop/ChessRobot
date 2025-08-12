/*
 * ========================================
 * 로봇팔 역기구학 제어 시스템
 * ========================================
 *
 * 이 프로그램은 3링크 로봇팔의 역기구학을 계산하여
 * 목표 위치에 도달할 수 있도록 서보 모터를 제어합니다.
 *
 * 하드웨어 구성:
 * - 베이스 (고정, 회전 안함)
 * - 어깨 관절 (서보 1, pitch 방향)
 * - 팔꿈치 관절 (서보 2, pitch 방향)
 * - 엔드 이펙터 (그리퍼 또는 도구)
 *
 * 작성자: [사용자명]
 * 날짜: [작성일]
 * ========================================
 */

#include <Wire.h>                    // I2C 통신을 위한 라이브러리
#include <Adafruit_PWMServoDriver.h> // PWM 서보 드라이버 제어 라이브러리
#include <math.h>                    // 수학 함수 (sin, cos, atan2 등)

// PWM 서보 드라이버 객체 생성
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

/*
 * ========================================
 * 로봇팔 물리적 사양 및 치수
 * ========================================
 * 모든 치수는 밀리미터(mm) 단위입니다.
 *
 * L1: 베이스에서 어깨 관절까지의 높이
 *      - 실제 하드웨어에서 베이스 플레이트 위의 서보 마운트 높이
 *      - Z축 방향의 오프셋 역할
 *
 * L2: 어깨 관절에서 팔꿈치 관절까지의 링크 길이
 *      - 첫 번째 서보 모터(어깨)가 제어하는 링크
 *      - 로봇팔의 주요 동작 범위 결정
 *
 * L3: 팔꿈치 관절에서 엔드 이펙터까지의 링크 길이
 *      - 두 번째 서보 모터(팔꿈치)가 제어하는 링크
 *      - 그리퍼나 도구를 포함한 최종 링크
 */
const float L1 = 95.0;  // 베이스 → 어깨 관절 높이 (mm)
const float L2 = 123.0; // 어깨 관절 → 팔꿈치 관절 링크 길이 (mm)
const float L3 = 200.0; // 팔꿈치 관절 → 엔드 이펙터 링크 길이 (mm)

/*
 * ========================================
 * 서보 모터 설정 및 제어 파라미터
 * ========================================
 *
 * 서보 모터는 PWM(Pulse Width Modulation) 신호로 제어됩니다.
 * PWM 값의 범위는 일반적으로 150~500이며, 이는 서보 모터의
 * 물리적 한계와 안전한 동작 범위를 고려한 값입니다.
 *
 * PWM 값과 각도의 관계:
 * - 150: 서보 모터의 최소 위치 (한쪽 끝)
 * - 375: 서보 모터의 중립 위치 (중앙)
 * - 500: 서보 모터의 최대 위치 (다른 쪽 끝)
 *
 * 주의: 실제 하드웨어에 맞게 이 값들을 조정해야 합니다.
 * ========================================
 */

// 전체 서보 모터 개수 (PCA9685 드라이버는 최대 16개 채널 지원)
const int numServos = 6;

// 각 서보 모터의 현재 PWM 위치를 저장하는 배열
// 초기값은 안전한 중립 위치로 설정
int servoPositions[numServos] = {375, 440, 450, 375, 375, 375};

/*
 * 서보 모터 설정 구조체
 * 각 서보 모터의 특성과 제한사항을 정의합니다.
 */
struct ServoConfig
{
    int neutralPWM;    // 중립 위치 PWM 값 (서보 모터가 정지한 상태)
    int minPWM;        // 최소 PWM 값 (물리적 한계, 더 작으면 서보 손상 가능)
    int maxPWM;        // 최대 PWM 값 (물리적 한계, 더 크면 서보 손상 가능)
    float minAngle;    // 최소 각도 (도 단위, -90도)
    float maxAngle;    // 최대 각도 (도 단위, +90도)
    float offsetAngle; // 각도 오프셋 (도 단위, 하드웨어 보정용)
};

/*
 * 각 서보 모터별 상세 설정
 *
 * 서보 0: 베이스 yaw 모터 (현재 사용하지 않음)
 *          - 고정 위치에 설치되어 회전하지 않음
 *          - 향후 확장을 위해 예약
 *
 * 서보 1: 어깨 pitch 모터 (로봇팔의 주요 동작)
 *          - 수평 위치: PWM 440 (0도)
 *          - Y축 수평에서 Z축 수평까지 회전
 *
 * 서보 2: 팔꿈치 pitch 모터 (로봇팔의 세밀한 동작)
 *          - 수평 위치: PWM 450 (0도)
 *          - 쭉 뻗은 상태에서 접힌 상태까지 회전
 *
 * 서보 3-5: 향후 확장을 위한 예약 채널
 */
ServoConfig servos[numServos] = {
    // 서보 0 (베이스 - yaw, 현재 사용 안함)
    {375, 150, 500, -90, 90, 0},
    // 서보 1 (어깨 - pitch) - 수평 위치: 440
    {440, 150, 500, -90, 90, 0},
    // 서보 2 (팔꿈치 - pitch) - 수평 위치: 450
    {450, 150, 500, -90, 90, 0},
    // 서보 3-5 (사용 안함, 향후 확장용)
    {375, 150, 500, -90, 90, 0},
    {375, 150, 500, -90, 90, 0},
    {375, 150, 500, -90, 90, 0}};

/*
 * ========================================
 * 전역 변수 및 상태 관리
 * ========================================
 *
 * 이 변수들은 로봇팔의 현재 상태와 목표 상태를
 * 추적하고 관리하는 데 사용됩니다.
 * ========================================
 */

// 목표 위치 좌표 (Y, Z 평면만 사용, X는 항상 0)
// Y: 전후 방향 (양수 = 앞쪽, 음수 = 뒤쪽)
// Z: 상하 방향 (양수 = 위쪽, 음수 = 아래쪽)
float targetY = 0.0; // 목표 Y 좌표 (mm)
float targetZ = 0.0; // 목표 Z 좌표 (mm)

/*
 * 현재 관절 각도 (도 단위)
 *
 * theta1: 베이스 회전 각도 (현재 항상 0도)
 *          - yaw 모터가 없어서 회전하지 않음
 *          - 향후 확장을 위해 예약
 *
 * theta2: 어깨 관절 각도 (서보 1이 제어)
 *          - 0도: Y축 수평 (팔이 오른쪽으로 뻗음)
 *          - 90도: Z축 수평 (팔이 위로 뻗음)
 *          - 양수: 반시계방향 회전
 *
 * theta3: 팔꿈치 관절 각도 (서보 2가 제어)
 *          - 0도: 쭉 뻗음 (팔꿈치 펴짐)
 *          - 90도: 접힘 (팔꿈치 접힘)
 *          - 양수: 반시계방향 회전
 */
float theta1 = 0.0; // 베이스 회전 각도 (항상 0도)
float theta2 = 0.0; // 어깨 관절 각도 (서보 1)
float theta3 = 0.0; // 팔꿈치 관절 각도 (서보 2)

/*
 * 시리얼 통신을 위한 버퍼 변수
 *
 * inputString: 사용자로부터 입력받은 명령어 문자열
 * stringComplete: 입력이 완료되었는지 나타내는 플래그
 *
 * 시리얼 모니터를 통해 실시간으로 로봇팔을 제어할 수 있습니다.
 */
String inputString = "";     // 입력 문자열 버퍼
bool stringComplete = false; // 입력 완료 플래그

/*
 * ========================================
 * Arduino 초기화 함수
 * ========================================
 *
 * 이 함수는 Arduino가 전원을 켜거나 리셋될 때
 * 한 번만 실행되며, 시스템 초기화를 담당합니다.
 * ========================================
 */
void setup()
{
    /*
     * 시리얼 통신 초기화
     * 9600 baud rate로 설정하여 컴퓨터와 통신
     * 시리얼 모니터에서 로봇팔을 제어할 수 있음
     */
    Serial.begin(9600);

    /*
     * PWM 서보 드라이버 초기화
     * PCA9685 I2C 서보 드라이버를 초기화하고
     * 50Hz PWM 주파수로 설정
     *
     * 50Hz는 표준 서보 모터의 동작 주파수입니다.
     * 이 주파수에서 1.5ms 펄스가 중립 위치를 의미합니다.
     */
    pwm.begin();
    pwm.setPWMFreq(50);

    /*
     * 안정화를 위한 지연
     * 서보 드라이버가 완전히 초기화될 때까지 대기
     */
    delay(10);

    /*
     * ========================================
     * 사용자 인터페이스 및 도움말 출력
     * ========================================
     *
     * 시리얼 모니터에 시스템 정보와 사용법을 표시합니다.
     * 사용자는 이 정보를 바탕으로 로봇팔을 제어할 수 있습니다.
     */
    Serial.println("=== 역기구학 로봇팔 제어 시스템 ===");
    Serial.println("이 시스템은 3링크 로봇팔을 역기구학으로 제어합니다.");
    Serial.println();

    Serial.println("=== 기본 사용법 ===");
    Serial.println("Y값만 입력하면 됩니다 (예: 100)");
    Serial.println("Y: 전후 방향 (mm), Z는 100mm로 고정");
    Serial.println();

    Serial.println("=== 사용 가능한 명령어 ===");
    Serial.println("  home: 홈 포지션으로 이동 (안전한 초기 위치)");
    Serial.println("  angle1,30: 서보 1(어깨)을 30도로 이동");
    Serial.println("  angle2,-45: 서보 2(팔꿈치)를 -45도로 이동");
    Serial.println();

    Serial.println("=== PWM 테스트 명령어 ===");
    Serial.println("  test1,100: 서보 1을 PWM 100으로 테스트");
    Serial.println("  test2,600: 서보 2를 PWM 600으로 테스트");
    Serial.println("  sweep1: 서보 1을 100~600 범위로 자동 테스트");
    Serial.println("  sweep2: 서보 2를 100~600 범위로 자동 테스트");
    Serial.println("  stop: 모든 서보 정지 (비상 정지)");
    Serial.println("================================");

    /*
     * 초기 위치 설정
     * 로봇팔을 안전한 홈 포지션으로 이동시킵니다.
     * 이는 시스템 시작 시 로봇팔이 예측 가능한
     * 상태에 있도록 보장합니다.
     */
    moveToHomePosition();
}

/*
 * ========================================
 * Arduino 메인 루프 함수
 * ========================================
 *
 * 이 함수는 Arduino가 실행되는 동안 계속 반복 실행됩니다.
 * 시리얼 통신을 통해 사용자 명령을 처리하고
 * 로봇팔을 제어하는 메인 로직을 담당합니다.
 * ========================================
 */
void loop()
{
    /*
     * 시리얼 입력 처리
     * 사용자가 시리얼 모니터를 통해 명령을 입력하면
     * stringComplete 플래그가 true가 되고,
     * 이때 입력된 명령을 처리합니다.
     */
    if (stringComplete)
    {
        processSerialInput();   // 입력된 명령 처리
        inputString = "";       // 입력 버퍼 초기화
        stringComplete = false; // 처리 완료 플래그 리셋
    }

    /*
     * 주의: 이 루프는 매우 빠르게 실행되므로
     * delay() 함수를 사용하지 않습니다.
     * 서보 모터 제어는 별도 함수에서 처리됩니다.
     */
}

/*
 * ========================================
 * 시리얼 통신 이벤트 핸들러
 * ========================================
 *
 * 이 함수는 시리얼 통신으로 데이터가 들어올 때마다
 * 자동으로 호출됩니다. 사용자 입력을 버퍼에 저장하고
 * 입력 완료를 감지합니다.
 * ========================================
 */
void serialEvent()
{
    /*
     * 시리얼 버퍼에 데이터가 있는 동안 반복
     * 여러 문자가 연속으로 들어올 수 있음
     */
    while (Serial.available())
    {
        // 한 문자씩 읽어서 처리
        char inChar = (char)Serial.read();

        if (inChar == '\n') // 줄바꿈 문자 (Enter 키)
        {
            stringComplete = true; // 입력 완료 플래그 설정
        }
        else // 일반 문자
        {
            inputString += inChar; // 입력 버퍼에 문자 추가
        }
    }

    /*
     * 입력 처리 방식:
     * 1. 사용자가 "100" 입력 후 Enter
     * 2. "100"이 inputString에 저장됨
     * 3. Enter 키(\n)가 감지되면 stringComplete = true
     * 4. loop()에서 stringComplete가 true인 것을 확인
     * 5. processSerialInput() 호출하여 "100" 처리
     */
}

void processSerialInput()
{
    inputString.trim();

    if (inputString.equalsIgnoreCase("home"))
    {
        Serial.println("홈 포지션으로 이동...");
        moveToHomePosition();
        return;
    }

    if (inputString.equalsIgnoreCase("stop"))
    {
        Serial.println("모든 서보 정지...");
        stopAllServos();
        return;
    }

    if (inputString.equalsIgnoreCase("sweep1"))
    {
        Serial.println("서보 1 스윕 테스트 시작...");
        sweepTest(1);
        return;
    }

    if (inputString.equalsIgnoreCase("sweep2"))
    {
        Serial.println("서보 2 스윕 테스트 시작...");
        sweepTest(2);
        return;
    }

    if (inputString.startsWith("test"))
    {
        testPWM(inputString);
        return;
    }

    if (inputString.startsWith("angle"))
    {
        testAngle(inputString);
        return;
    }

    // Y값만 입력받음 (Z는 100으로 고정 - 더 도달하기 쉬운 높이)
    targetY = inputString.toFloat();
    targetZ = 100.0; // Z값 고정

    Serial.print("목표 위치: Y=");
    Serial.print(targetY);
    Serial.print(", Z=");
    Serial.println(targetZ);

    // 역기구학 계산 및 실행
    Serial.println("역기구학 계산 중...");
    if (calculateInverseKinematics(targetY, targetZ))
    {
        Serial.println("계산 성공! 로봇팔 이동 중...");
        moveRobotArm();
    }
    else
    {
        Serial.println("오류: 도달할 수 없는 위치입니다.");
    }
}

bool calculateInverseKinematics(float y, float z)
{
    // 2D 평면에서의 역기구학 계산 (YZ 평면)
    // X는 항상 0이므로 theta1도 항상 0

    // L1을 고려한 상대적 Z 좌표 계산
    float z_offset = z;
    float r = sqrt(y * y + z_offset * z_offset);

    // 도달 가능한 범위 확인 (L2 + L3만 고려)
    float maxReach = L2 + L3;
    float minReach = abs(L2 - L3);

    // Z 오프셋이 너무 작으면 도달 불가능
    // L1(95mm)을 고려했을 때, Z가 너무 낮으면 물리적으로 도달 불가능
    // if (z_offset < -L1)
    // {
    //     Serial.print("Z 오프셋이 너무 작음: ");
    //     Serial.print(z_offset);
    //     Serial.print("mm (최소 -");
    //     Serial.print(L1);
    //     Serial.println("mm)");
    //     return false;
    // }

    if (r > maxReach || r < minReach)
    {
        Serial.print("거리 오류: r = ");
        Serial.print(r);
        Serial.print(", 범위: ");
        Serial.print(minReach);
        Serial.print(" ~ ");
        Serial.println(maxReach);
        Serial.print("Z 오프셋: ");
        Serial.println(z_offset);
        return false;
    }

    // theta1은 항상 0 (yaw 모터 없음)
    theta1 = 0.0;

    // 내 계산값
    // float D = (y * y + z * z - L2 * L2 - L3 * L3) / (2 * L2 * L3);
    // float theta3 = -atan2(sqrt(1 - D * D), D);
    // float theta2 = atan2(z, y) - atan2(-L3 * sin(theta3), L2 + L3 * cos(theta3));

    // theta2, theta3 계산 (2링크 역기구학) - 웹 시각화와 동일한 수식
    float dy = y;
    float dz = z - L1;

    float rSquared = dy * dy + dz * dz;
    float D = (rSquared - L2 * L2 - L3 * L3) / (2 * L2 * L3);

    if (D < -1.0 || D > 1.0)
    {
        Serial.println("D 범위 오류");
        return false;
    }

    // 두 가지 해 계산 (elbow-down과 elbow-up)
    float theta3_1 = atan2(sqrt(1 - D * D), D);  // elbow-down
    float theta3_2 = atan2(-sqrt(1 - D * D), D); // elbow-up

    float theta2_1 = atan2(dz, dy) - atan2(L3 * sin(theta3_1), L2 + L3 * cos(theta3_1));
    float theta2_2 = atan2(dz, dy) - atan2(L3 * sin(theta3_2), L2 + L3 * cos(theta3_2));

    // 각도를 도 단위로 변환
    float theta2_deg_1 = theta2_1 * 180.0 / PI;
    float theta2_deg_2 = theta2_2 * 180.0 / PI;
    float theta3_deg_1 = theta3_1 * 180.0 / PI;
    float theta3_deg_2 = theta3_2 * 180.0 / PI;

    // 디버깅: 두 해 모두 출력
    Serial.println("=== 역기구학 계산 결과 ===");
    Serial.print("해 1 (elbow-down): theta2=");
    Serial.print(theta2_deg_1);
    Serial.print("°, theta3=");
    Serial.print(theta3_deg_1);
    Serial.println("°");
    Serial.print("해 2 (elbow-up): theta2=");
    Serial.print(theta2_deg_2);
    Serial.print("°, theta3=");
    Serial.print(theta3_deg_2);
    Serial.println("°");

    // 둘 중 theta2가 양수인 해 선택 (HTML 시각화와 동일)
    if (theta2_deg_1 > 0)
    {
        theta2 = theta2_deg_1;
        theta3 = theta3_deg_1;
        Serial.println("해 1 (elbow-down) 선택됨");
    }
    else
    {
        theta2 = theta2_deg_2;
        theta3 = theta3_deg_2;
        Serial.println("해 2 (elbow-up) 선택됨");
    }

    // theta3는 L2-L3 사이의 관절 각도이므로 그대로 유지
    // (헤드 방향은 실제 하드웨어 구조에 따라 결정됨)

    // 각도 범위 확인 (제한 해제)
    Serial.println("=== 각도 범위 확인 ===");
    Serial.print("theta2: ");
    Serial.print(theta2);
    Serial.println("° (제한 해제됨)");

    Serial.print("theta3: ");
    Serial.print(theta3);
    Serial.println("° (제한 해제됨)");

    // 각도 오프셋 적용
    float theta2_before_offset = theta2;
    float theta3_before_offset = theta3;
    theta2 += servos[1].offsetAngle;
    theta3 += servos[2].offsetAngle;

    Serial.println("=== 최종 각도 ===");
    Serial.print("theta1: ");
    Serial.print(theta1);
    Serial.println("° (베이스 회전, 항상 0)");
    Serial.print("theta2: ");
    Serial.print(theta2_before_offset);
    Serial.print("° → ");
    Serial.print(theta2);
    Serial.println("° (어깨 관절)");
    Serial.print("theta3: ");
    Serial.print(theta3_before_offset);
    Serial.print("° → ");
    Serial.print(theta3);
    Serial.println("° (팔꿈치 관절)");
    Serial.print("Z 오프셋: ");
    Serial.println(z_offset);
    Serial.println("==================");

    return true;
}

void moveRobotArm()
{
    Serial.println("=== PWM 변환 및 서보 제어 ===");

    // 각도를 PWM 값으로 변환 (수직=0도, 수평=90도, 아래로 갈수록 각도 커짐)
    int servo0 = servos[0].neutralPWM;
    Serial.print("서보 0 (베이스): ");
    Serial.print(servo0);
    Serial.println(" (고정값)");

    // theta2 -> 서보 1 (어깨) - 0도=Y축 수평(230), 90도=Z축 수평(440)
    int servo1;
    if (abs(theta2) < 0.1)
    {
        servo1 = 230; // 0도(Y축 수평)
        Serial.print("서보 1 (어깨): ");
        Serial.print(servo1);
        Serial.println(" (0도 - Y축 수평)");
    }
    else
    {
        // 0도=230(Y축 수평), 90도=440(Z축 수평)
        float pwmPerDegree = (440.0 - 230.0) / 90.0; // 2.33
        int calculatedPWM = 230 + (int)(theta2 * pwmPerDegree);
        servo1 = calculatedPWM; // 정확한 PWM 값 사용

        // PWM 범위 경고 (하드웨어 제한)
        if (servo1 < 150)
        {
            Serial.print("경고: 서보 1 PWM이 하한선을 초과 (");
            Serial.print(servo1);
            Serial.println(" < 150)");
        }
        else if (servo1 > 500)
        {
            Serial.print("경고: 서보 1 PWM이 상한선을 초과 (");
            Serial.print(servo1);
            Serial.println(" > 500)");
        }

        Serial.print("서보 1 (어깨): ");
        Serial.print(servo1);
        Serial.print(" (");
        Serial.print(theta2);
        Serial.print("° → PWM ");
        Serial.print(calculatedPWM);
        Serial.println(")");
    }

    // theta3 -> 서보 2 (팔꿈치) - 0도=쭉 뻗음(450), 90도=접힘(240)
    int servo2;
    if (abs(theta3) < 0.1)
    {
        servo2 = 450; // 0도(쭉 뻗음)
        Serial.print("서보 2 (팔꿈치): ");
        Serial.print(servo2);
        Serial.println(" (0도 - 쭉 뻗음)");
    }
    else
    {
        // 0도=450(쭉 뻗음), 90도=240(접힘)
        float pwmPerDegree = (450.0 - 240.0) / 90.0; // 2.33
        int calculatedPWM = 450 + (int)(theta3 * pwmPerDegree);
        servo2 = calculatedPWM; // 정확한 PWM 값 사용

        // PWM 범위 경고 (하드웨어 제한)
        if (servo2 < 150)
        {
            Serial.print("경고: 서보 2 PWM이 하한선을 초과 (");
            Serial.print(servo2);
            Serial.println(" < 150)");
        }
        else if (servo2 > 500)
        {
            Serial.print("경고: 서보 2 PWM이 상한선을 초과 (");
            Serial.print(servo2);
            Serial.println(" > 500)");
        }

        Serial.print("서보 2 (팔꿈치): ");
        Serial.print(servo2);
        Serial.print(" (");
        Serial.print(theta3);
        Serial.print("° → PWM ");
        Serial.print(calculatedPWM);
        Serial.println(")");
    }

    // 서보 모터 제어
    Serial.println("서보 모터 제어 중...");
    pwm.setPWM(0, 0, servo0);
    pwm.setPWM(1, 0, servo1);
    pwm.setPWM(2, 0, servo2);

    servoPositions[0] = servo0;
    servoPositions[1] = servo1;
    servoPositions[2] = servo2;

    Serial.println("=== 최종 PWM 값 ===");
    Serial.print("서보 0: ");
    Serial.print(servo0);
    Serial.print(", 서보 1: ");
    Serial.print(servo1);
    Serial.print(", 서보 2: ");
    Serial.println(servo2);
    Serial.println("==================");

    delay(1000);
}

void moveToHomePosition()
{
    // 제로(수평) 홈 포지션으로 이동
    theta1 = 0.0;
    theta2 = 90.0; // 수평
    theta3 = 0.0;  // 수평

    moveRobotArm();
    Serial.println("제로 홈 포지션 도달");
}

void testAngle(String input)
{
    // angle1,30 또는 angle2,-45 형식 처리
    int commaIndex = input.indexOf(',');
    if (commaIndex == -1)
    {
        Serial.println("오류: angle1,30 형식으로 입력하세요");
        return;
    }

    String servoStr = input.substring(5, commaIndex); // "angle" 제거
    String angleStr = input.substring(commaIndex + 1);

    int servoIndex = servoStr.toInt();
    float angle = angleStr.toFloat();

    if (servoIndex < 1 || servoIndex > 2)
    {
        Serial.println("오류: 서보 1 또는 2만 사용 가능");
        return;
    }

    Serial.print("서보 ");
    Serial.print(servoIndex);
    Serial.print("를 ");
    Serial.print(angle);
    Serial.println("도로 이동");

    // 각도 범위 확인 (제한 해제)
    Serial.print("입력된 각도: ");
    Serial.print(angle);
    Serial.println("° (제한 해제됨)");

    // 해당 서보만 이동
    if (servoIndex == 1)
    {
        theta2 = angle;
        // theta3은 현재 값 유지
    }
    else if (servoIndex == 2)
    {
        theta3 = angle;
        // theta2는 현재 값 유지
    }

    // 각도를 PWM 값으로 변환 (실제 측정된 PWM-각도 관계 사용)
    int servo0 = servos[0].neutralPWM; // 베이스 중립

    // theta2 -> 서보 1 (어깨)
    int servo1;
    if (servoIndex == 1)
    {
        // 서보 1을 직접 제어 (실제 측정된 PWM-각도 관계 사용)
        if (abs(angle) < 0.1) // 0도 근처
        {
            servo1 = 230; // Y축 수평 위치
        }
        else
        {
            // 실제 측정된 PWM-각도 관계로 계산
            // PWM 230 = 0도(Y축 수평), PWM 440 = 90도(Z축 수평)
            float pwmPerDegree = (440.0 - 230.0) / 90.0; // 2.33
            int calculatedPWM = 230 + (int)(angle * pwmPerDegree);
            servo1 = calculatedPWM; // 정확한 PWM 값 사용

            // PWM 범위 경고 (하드웨어 제한)
            if (servo1 < 150)
            {
                Serial.print("경고: 서보 1 PWM이 하한선을 초과 (");
                Serial.print(servo1);
                Serial.println(" < 150)");
            }
            else if (servo1 > 500)
            {
                Serial.print("경고: 서보 1 PWM이 상한선을 초과 (");
                Serial.print(servo1);
                Serial.println(" > 500)");
            }
        }
    }
    else
    {
        // 서보 1은 현재 위치 유지
        servo1 = servoPositions[1];
    }

    // theta3 -> 서보 2 (팔꿈치)
    int servo2;
    if (servoIndex == 2)
    {
        // 서보 2를 직접 제어 (실제 측정된 PWM-각도 관계 사용)
        if (abs(angle) < 0.1) // 0도 근처
        {
            servo2 = 450; // 쭉 뻗음 위치
        }
        else
        {
            // 실제 측정된 PWM-각도 관계로 계산
            // PWM 450 = 0도(쭉 뻗음), PWM 240 = 90도(접힘)
            float pwmPerDegree = (450.0 - 240.0) / 90.0; // 2.33
            int calculatedPWM = 450 - (int)(angle * pwmPerDegree);
            servo2 = calculatedPWM; // 정확한 PWM 값 사용

            // PWM 범위 경고 (하드웨어 제한)
            if (servo2 < 150)
            {
                Serial.print("경고: 서보 2 PWM이 하한선을 초과 (");
                Serial.print(servo2);
                Serial.println(" < 150)");
            }
            else if (servo2 > 500)
            {
                Serial.print("경고: 서보 2 PWM이 상한선을 초과 (");
                Serial.print(servo2);
                Serial.println(" > 500)");
            }
        }
    }
    else
    {
        // 서보 2는 현재 위치 유지
        servo2 = servoPositions[2];
    }

    // 서보 모터 제어
    pwm.setPWM(0, 0, servo0);
    pwm.setPWM(1, 0, servo1);
    pwm.setPWM(2, 0, servo2);

    // 위치 업데이트
    servoPositions[0] = servo0;
    servoPositions[1] = servo1;
    servoPositions[2] = servo2;

    Serial.print("서보 PWM 값 - 0: ");
    Serial.print(servo0);
    Serial.print(", 1: ");
    Serial.print(servo1);
    Serial.print(", 2: ");
    Serial.println(servo2);

    // 각도 설명 출력
    Serial.println("=== 각도 설명 ===");
    Serial.println("theta2 (서보 1): 어깨 관절");
    Serial.println("  0도: Y축 수평 (PWM: 230) - 팔 오른쪽");
    Serial.println("  90도: Z축 수평 (PWM: 440) - 팔 위로");
    Serial.println("  +각도: 반시계방향 회전 (PWM 증가)");
    Serial.println("  -각도: 시계방향 회전 (PWM 감소)");
    Serial.println();
    Serial.println("theta3 (서보 2): 팔꿈치 관절");
    Serial.println("  0도: 쭉 뻗음 (PWM: 450) - 팔꿈치 펴짐");
    Serial.println("  90도: 접힘 (PWM: 240) - 팔꿈치 접힘");
    Serial.println("  +각도: 반시계방향 회전 (PWM 감소)");
    Serial.println("  -각도: 시계방향 회전 (PWM 증가)");
    Serial.println("==================");

    // 현재 위치에서의 정기구학 계산
    Serial.println("=== 현재 위치 정기구학 ===");
    float t2_rad = theta2 * PI / 180.0;
    float t3_rad = theta3 * PI / 180.0;

    // 어깨 위치 (베이스 기준)
    float shoulderY = 0;
    float shoulderZ = L1;

    // 팔꿈치 위치
    float elbowY = shoulderY + L2 * cos(t2_rad);
    float elbowZ = shoulderZ + L2 * sin(t2_rad);

    // 엔드 이펙터 위치
    float endY = elbowY + L3 * cos(t2_rad + t3_rad);
    float endZ = elbowZ + L3 * sin(t2_rad + t3_rad);

    Serial.print("어깨 위치: (");
    Serial.print(shoulderY);
    Serial.print(", ");
    Serial.print(shoulderZ);
    Serial.println(")");
    Serial.print("팔꿈치 위치: (");
    Serial.print(elbowY);
    Serial.print(", ");
    Serial.print(elbowZ);
    Serial.println(")");
    Serial.print("엔드 이펙터 위치: (");
    Serial.print(endY);
    Serial.print(", ");
    Serial.print(endZ);
    Serial.println(")");
    Serial.println("========================");
}

void testPWM(String input)
{
    // test1,100 또는 test2,600 형식 처리
    int commaIndex = input.indexOf(',');
    if (commaIndex == -1)
    {
        Serial.println("오류: test1,100 형식으로 입력하세요");
        return;
    }

    String servoStr = input.substring(4, commaIndex); // "test" 제거
    String pwmStr = input.substring(commaIndex + 1);

    int servoIndex = servoStr.toInt();
    int pwmValue = pwmStr.toInt();

    if (servoIndex < 1 || servoIndex > 2)
    {
        Serial.println("오류: 서보 1 또는 2만 테스트 가능");
        return;
    }

    if (pwmValue < 0 || pwmValue > 1000)
    {
        Serial.println("오류: PWM 값은 0~1000 범위여야 합니다");
        return;
    }

    Serial.print("서보 ");
    Serial.print(servoIndex);
    Serial.print("를 PWM ");
    Serial.print(pwmValue);
    Serial.println("으로 테스트");

    // 안전 확인
    Serial.println("3초 후 PWM 값이 적용됩니다. 서보 모터를 확인하세요.");
    delay(3000);

    // PWM 적용
    pwm.setPWM(servoIndex, 0, pwmValue);
    servoPositions[servoIndex] = pwmValue;

    Serial.print("서보 ");
    Serial.print(servoIndex);
    Serial.print(" PWM ");
    Serial.print(pwmValue);
    Serial.println(" 적용됨");

    // 5초 후 홈으로 복귀
    Serial.println("5초 후 홈 포지션으로 복귀합니다.");
    delay(5000);
    moveToHomePosition();
}

void sweepTest(int servoIndex)
{
    Serial.print("서보 ");
    Serial.print(servoIndex);
    Serial.println(" 스윕 테스트 시작");
    Serial.println("각 PWM 값에서 1초씩 대기합니다.");

    // 100부터 600까지 50씩 증가
    for (int pwmValue = 100; pwmValue <= 600; pwmValue += 50)
    {
        Serial.print("PWM ");
        Serial.print(pwmValue);
        Serial.println(" 테스트 중...");

        pwm.setPWM(servoIndex, 0, pwmValue);
        servoPositions[servoIndex] = pwmValue;

        delay(1000);
    }

    Serial.println("스윕 테스트 완료. 홈으로 복귀합니다.");
    moveToHomePosition();
}

void stopAllServos()
{
    // 모든 서보 모터 정지
    for (int i = 0; i < numServos; i++)
    {
        pwm.setPWM(i, 0, 0); // PWM 0으로 정지
    }
    Serial.println("모든 서보 정지됨");
}
