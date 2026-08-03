/*
 * ESP32-S3 USB Keyboard Bridge - Firmware
 *
 * Convierte el ESP32-S3 en un puente entre:
 * - UART (Serial): recibe comandos desde la laptop
 * - USB HID: actua como teclado para el desktop
 *
 * Protocolo: 2 bytes por evento
 * Byte 0: Tipo de evento (0x01=PRESS, 0x00=RELEASE)
 * Byte 1: Codigo HID crudo de la tecla (tabla USB HID)
 *
 * NOTA IMPORTANTE: se usan pressRaw()/releaseRaw() porque los codigos
 * que envia la laptop son USAGE CODES crudos (0x04=A, 0x28=ENTER, ...).
 * press()/release() interpretan ASCII y servirian para otro protocolo.
 *
 * Configuracion de placa requerida (arduino-cli):
 *   --fqbn esp32:esp32:esp32s3:USBMode=default
 *   (USBMode=default = USB-OTG/TinyUSB, activa el HID en el puerto nativo)
 */

#include "USB.h"
#include "USBHIDKeyboard.h"

// --- Configuracion -----------------------------------------------------
#define SERIAL_BAUD     115200
#define EVENT_PRESS     0x01
#define EVENT_RELEASE   0x00
#define LED_PIN         2
//#define DEBUG          // descomentar para ver traza en el Serial

// Instancia del teclado USB HID
USBHIDKeyboard Keyboard;

// Buffer para recibir los paquetes de 2 bytes
uint8_t rxBuffer[2];
uint8_t bufferIndex = 0;

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Serial = UART0 (esta cableado al puente USB->UART de la placa)
  Serial.begin(SERIAL_BAUD);

  // Inicializar el teclado USB HID y el USB nativo (TinyUSB)
  Keyboard.begin();
  USB.begin();

  Serial.println("ESP32-S3 Keyboard Bridge iniciado");
  Serial.println("Esperando comandos por UART...");
  digitalWrite(LED_PIN, HIGH);
}

void loop() {
  // Leer todos los bytes disponibles del UART
  while (Serial.available() > 0) {
    uint8_t byteLeido = Serial.read();

    if (bufferIndex < 2) {
      rxBuffer[bufferIndex] = byteLeido;
      bufferIndex++;

      if (bufferIndex == 2) {
        procesarEvento(rxBuffer[0], rxBuffer[1]);
        bufferIndex = 0;
      }
    }
  }

  delay(1);
}

/**
 * Procesa un evento recibido por UART.
 * @param tipoEvento 0x01=press, 0x00=release
 * @param codigoHID  usage code USB HID crudo
 */
void procesarEvento(uint8_t tipoEvento, uint8_t codigoHID) {
  if (codigoHID == 0x00) {
#ifdef DEBUG
    Serial.println("ERROR: Codigo HID invalido (0x00)");
#endif
    return;
  }

#ifdef DEBUG
  Serial.print("Evento: ");
  Serial.print(tipoEvento == EVENT_PRESS ? "PRESS" : "RELEASE");
  Serial.print(" | HID: 0x");
  Serial.println(codigoHID, HEX);
#endif

  if (tipoEvento == EVENT_PRESS) {
    Keyboard.pressRaw(codigoHID);
  } else if (tipoEvento == EVENT_RELEASE) {
    Keyboard.releaseRaw(codigoHID);
  } else {
#ifdef DEBUG
    Serial.print("ERROR: Tipo de evento invalido: 0x");
    Serial.println(tipoEvento, HEX);
#endif
  }
}

/**
 * Prueba sin UART: envia ENTER cada 2 segundos.
 * Descomentar la llamada en loop() para verificar el HID en el desktop.
 */
void enviarTeclaPrueba() {
  static unsigned long lastTime = 0;
  unsigned long currentTime = millis();

  if (currentTime - lastTime > 2000) {
    lastTime = currentTime;
    Serial.println("Prueba: ENTER (HID 0x28)");
    Keyboard.pressRaw(0x28);
    delay(50);
    Keyboard.releaseRaw(0x28);
  }
}

// Descomentar la siguiente linea en loop() para probar el HID sin UART:
// enviarTeclaPrueba();
