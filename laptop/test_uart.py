#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script para probar la comunicacion UART con el ESP32.
Envia teclas de prueba para verificar que el HID funciona.

Uso: python3 test_uart.py [/dev/ttyACM0]
"""

import sys
import time
import serial


def test_uart(serial_port='/dev/ttyACM0', baudrate=115200):
    try:
        ser = serial.Serial(serial_port, baudrate, timeout=1)
        print(f"Conectado a {serial_port}")

        # Esperar a que el ESP32 se inicialice
        time.sleep(2)

        # (tipo, codigo HID)
        test_keys = [
            (0x01, 0x04),  # PRESS A
            (0x00, 0x04),  # RELEASE A
            (0x01, 0x05),  # PRESS B
            (0x00, 0x05),  # RELEASE B
            (0x01, 0x28),  # PRESS ENTER
            (0x00, 0x28),  # RELEASE ENTER
            (0x01, 0x2C),  # PRESS SPACE
            (0x00, 0x2C),  # RELEASE SPACE
        ]

        print("Enviando teclas de prueba...")
        for tipo, codigo in test_keys:
            packet = bytes([tipo, codigo])
            ser.write(packet)
            ser.flush()

            tipo_str = "PRESS" if tipo == 0x01 else "RELEASE"
            print(f"  {tipo_str} HID=0x{codigo:02X}")
            time.sleep(0.5)

        print("Prueba completada")

    except FileNotFoundError:
        print(f"Puerto serial {serial_port} no encontrado")
        print("  Verifica que el ESP32 este conectado")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'ser' in locals():
            ser.close()


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyACM0'
    test_uart(port)
