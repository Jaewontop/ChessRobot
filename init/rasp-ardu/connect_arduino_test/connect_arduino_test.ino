String input = "";

void setup() {
  Serial.begin(9600);
  pinMode(13, OUTPUT);  // 내장 LED
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\n') {
      Serial.print("받은 값: ");
      Serial.println(input);

      if (input == "7") {
        digitalWrite(13, HIGH);
        delay(500);  // 0.5초
        digitalWrite(13, LOW);
      }

      input = "";  // 초기화
    } else {
      input += c;
    }
  }
}
