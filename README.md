# ESP32-S3 KeyBridge

Convierte tu **teclado de laptop** en un **teclado USB externo** para otra computadora, usando un ESP32-S3 como puente.

```
[Teclado laptop] --> [capturador en laptop] --UART--> [ESP32-S3] --USB HID--> [desktop PC]
```

## Arquitectura

- **Firmware** (`firmware/`): el ESP32-S3 se presenta como teclado USB HID por su puerto USB nativo (TinyUSB). Lee eventos por UART y los emite como teclas HID.
- **Laptop** (`laptop/`): captura las teclas físicas con `evdev`, las traduce a códigos USB HID y las envía por serial al ESP32.
- **Toggle por atajo**: presiona `F9+F10` para encender (el teclado y el ratón van solo al desktop) y apagar (vuelven a ser normales de la laptop). Se usa `F9+F10` y no Ctrl/Alt para que las combinaciones con Ctrl/Alt y la tecla `B` sigan funcionando en el desktop (cámbialo con `--toggle`).

## Conexión

- Puerto **UART** del ESP32 (CH340) -> laptop
- Puerto **USB nativo** del ESP32 -> desktop PC (aparece como teclado)

## Uso

```bash
# Laptop
pip install evdev pyserial
python3 laptop/keyboard_bridge.py

# Flashear firmware
arduino-cli compile --fqbn esp32:esp32:esp32s3:USBMode=default firmware/esp32s3_keybridge
arduino-cli upload -p /dev/ttyACM0 --fqbn esp32:esp32:esp32s3:USBMode=default firmware/esp32s3_keybridge
```

## Ramas

- **`main`**: solo teclado.
- **`mouse`**: teclado + ratón.
