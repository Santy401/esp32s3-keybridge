/*
 * ESP32-S3 USB Keyboard Bridge - Firmware
 *
 * Convierte el ESP32-S3 en un puente entre:
 * - UART (Serial): recibe comandos desde la laptop
 * - USB HID: actua como teclado para el desktop
 *
 * Protocolo (bytes de longitud variable segun el tipo):
 *   Teclado (2 bytes):
 *     [0x01=PRESS | 0x00=RELEASE] [codigo HID crudo]
 *   Raton - mover (4 bytes):
 *     [0x02] [dx] [dy] [rueda]        (dx, dy, rueda como int8 con signo)
 *   Raton - botones (2 bytes):
 *     [0x03=PRESS | 0x04=RELEASE] [boton HID]
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
#include "USBHIDMouse.h"

// --- Configuracion -----------------------------------------------------
#define SERIAL_BAUD     115200
#define EVENT_RELEASE   0x00
#define EVENT_PRESS     0x01
#define EVENT_MOUSE_MOVE    0x02
#define EVENT_MOUSE_PRESS   0x03
#define EVENT_MOUSE_RELEASE 0x04
#define LED_PIN         2
//#define DEBUG          // descomentar para ver traza en el Serial

// Instancias HID (teclado + raton) sobre el mismo puerto USB nativo
USBHIDKeyboard Keyboard;
USBHIDRelativeMouse Mouse;

// Buffer para recibir los paquetes (max 4 bytes) y estado del framing
uint8_t rxBuffer[4];
uint8_t bufferIndex = 0;
uint8_t frameLen = 0;

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Serial = UART0 (esta cableado al puente USB->UART de la placa)
  Serial.begin(SERIAL_BAUD);

  // Inicializar teclado + raton USB HID y el USB nativo (TinyUSB)
  Keyboard.begin();
  Mouse.begin();
  USB.begin();

  Serial.println("ESP32-S3 Keyboard+Mouse Bridge iniciado");
  Serial.println("Esperando comandos por UART...");
  digitalWrite(LED_PIN, HIGH);
}

/**
 * Longitud total del frame segun el byte de tipo (0 si es invalido).
 */
uint8_t longitudEvento(uint8_t tipo) {
  switch (tipo) {
    case EVENT_RELEASE:        // tecla soltar
    case EVENT_PRESS:          // tecla pulsar
    case EVENT_MOUSE_PRESS:    // boton raton pulsar
    case EVENT_MOUSE_RELEASE:  // boton raton soltar
      return 2;
    case EVENT_MOUSE_MOVE:     // mover raton (dx, dy, rueda)
      return 4;
    default:
      return 0;
  }
}

void loop() {
  // Leer todos los bytes disponibles del UART
  while (Serial.available() > 0) {
    uint8_t byteLeido = Serial.read();

    if (bufferIndex == 0) {
      frameLen = longitudEvento(byteLeido);
      if (frameLen == 0) {
#ifdef DEBUG
        Serial.print("ERROR: Tipo de evento invalido: 0x");
        Serial.println(byteLeido, HEX);
#endif
        continue;
      }
      rxBuffer[0] = byteLeido;
      bufferIndex = 1;
    } else {
      rxBuffer[bufferIndex] = byteLeido;
      bufferIndex++;
    }

    if (bufferIndex == frameLen) {
      procesarEvento(rxBuffer);
      bufferIndex = 0;
      frameLen = 0;
    }
  }

  delay(1);
}

/**
 * Procesa un frame completo recibido por UART.
 * @param buffer  frame: [tipo, payload...]
 */
void procesarEvento(uint8_t *buffer) {
  uint8_t tipo = buffer[0];

#ifdef DEBUG
  Serial.print("Frame: 0x");
  Serial.print(tipo, HEX);
  for (uint8_t i = 1; i < frameLen; i++) {
    Serial.print(" 0x");
    Serial.print(buffer[i], HEX);
  }
  Serial.println();
#endif

  switch (tipo) {
    case EVENT_PRESS:
      if (buffer[1] != 0x00) Keyboard.pressRaw(buffer[1]);
      break;
    case EVENT_RELEASE:
      if (buffer[1] != 0x00) Keyboard.releaseRaw(buffer[1]);
      break;
    case EVENT_MOUSE_MOVE:
      Mouse.move((int8_t)buffer[1], (int8_t)buffer[2], (int8_t)buffer[3]);
      break;
    case EVENT_MOUSE_PRESS:
      Mouse.press(buffer[1]);
      break;
    case EVENT_MOUSE_RELEASE:
      Mouse.release(buffer[1]);
      break;
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
