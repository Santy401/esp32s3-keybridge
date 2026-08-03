#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Keyboard/Mouse Bridge - Capturador y Traductor para Laptop

Este script:
1. Captura eventos del teclado fisico (ej: /dev/input/event3)
2. Captura eventos del raton (ej: /dev/input/event4)
3. Traduce keycodes de Linux a USB HID
4. Envia los eventos traducidos por UART al ESP32-S3
"""

import glob
import select
import argparse
import serial
from evdev import InputDevice, ecodes

ESP32_SERIAL_VIDS = {0x1A86, 0x10C4, 0x303A}  # CH340/CH341, CP210x, Espressif

# ============ TABLA DE TRADUCCION ============
# Mapeo de codigos de Linux (KEY_*) a usage codes USB HID crudos
# Fuente: https://www.usb.org/sites/default/files/documents/hut1_12v2.pdf

KEYMAP_LINUX_TO_HID = {
    # Letras
    ecodes.KEY_A: 0x04, ecodes.KEY_B: 0x05, ecodes.KEY_C: 0x06,
    ecodes.KEY_D: 0x07, ecodes.KEY_E: 0x08, ecodes.KEY_F: 0x09,
    ecodes.KEY_G: 0x0A, ecodes.KEY_H: 0x0B, ecodes.KEY_I: 0x0C,
    ecodes.KEY_J: 0x0D, ecodes.KEY_K: 0x0E, ecodes.KEY_L: 0x0F,
    ecodes.KEY_M: 0x10, ecodes.KEY_N: 0x11, ecodes.KEY_O: 0x12,
    ecodes.KEY_P: 0x13, ecodes.KEY_Q: 0x14, ecodes.KEY_R: 0x15,
    ecodes.KEY_S: 0x16, ecodes.KEY_T: 0x17, ecodes.KEY_U: 0x18,
    ecodes.KEY_V: 0x19, ecodes.KEY_W: 0x1A, ecodes.KEY_X: 0x1B,
    ecodes.KEY_Y: 0x1C, ecodes.KEY_Z: 0x1D,

    # Numeros (fila superior)
    ecodes.KEY_1: 0x1E, ecodes.KEY_2: 0x1F, ecodes.KEY_3: 0x20,
    ecodes.KEY_4: 0x21, ecodes.KEY_5: 0x22, ecodes.KEY_6: 0x23,
    ecodes.KEY_7: 0x24, ecodes.KEY_8: 0x25, ecodes.KEY_9: 0x26,
    ecodes.KEY_0: 0x27,

    # Teclas especiales
    ecodes.KEY_ENTER: 0x28,
    ecodes.KEY_ESC: 0x29,
    ecodes.KEY_BACKSPACE: 0x2A,
    ecodes.KEY_TAB: 0x2B,
    ecodes.KEY_SPACE: 0x2C,
    ecodes.KEY_MINUS: 0x2D,
    ecodes.KEY_EQUAL: 0x2E,
    ecodes.KEY_LEFTBRACE: 0x2F,
    ecodes.KEY_RIGHTBRACE: 0x30,
    ecodes.KEY_BACKSLASH: 0x31,
    ecodes.KEY_SEMICOLON: 0x33,
    ecodes.KEY_APOSTROPHE: 0x34,
    ecodes.KEY_GRAVE: 0x35,
    ecodes.KEY_COMMA: 0x36,
    ecodes.KEY_DOT: 0x37,
    ecodes.KEY_SLASH: 0x38,
    ecodes.KEY_CAPSLOCK: 0x39,

    # Modificadores
    ecodes.KEY_LEFTCTRL: 0xE0,
    ecodes.KEY_LEFTSHIFT: 0xE1,
    ecodes.KEY_LEFTALT: 0xE2,
    ecodes.KEY_LEFTMETA: 0xE3,   # Tecla Windows/Command
    ecodes.KEY_RIGHTCTRL: 0xE4,
    ecodes.KEY_RIGHTSHIFT: 0xE5,
    ecodes.KEY_RIGHTALT: 0xE6,
    ecodes.KEY_RIGHTMETA: 0xE7,

    # Teclas de funcion
    ecodes.KEY_F1: 0x3A, ecodes.KEY_F2: 0x3B, ecodes.KEY_F3: 0x3C,
    ecodes.KEY_F4: 0x3D, ecodes.KEY_F5: 0x3E, ecodes.KEY_F6: 0x3F,
    ecodes.KEY_F7: 0x40, ecodes.KEY_F8: 0x41, ecodes.KEY_F9: 0x42,
    ecodes.KEY_F10: 0x43, ecodes.KEY_F11: 0x44, ecodes.KEY_F12: 0x45,

    # Navegacion
    ecodes.KEY_INSERT: 0x49,
    ecodes.KEY_HOME: 0x4A,
    ecodes.KEY_PAGEUP: 0x4B,
    ecodes.KEY_DELETE: 0x4C,
    ecodes.KEY_END: 0x4D,
    ecodes.KEY_PAGEDOWN: 0x4E,
    ecodes.KEY_RIGHT: 0x4F,
    ecodes.KEY_LEFT: 0x50,
    ecodes.KEY_DOWN: 0x51,
    ecodes.KEY_UP: 0x52,

    # Teclado numerico
    ecodes.KEY_NUMLOCK: 0x53,
    ecodes.KEY_KPSLASH: 0x54,
    ecodes.KEY_KPASTERISK: 0x55,
    ecodes.KEY_KPMINUS: 0x56,
    ecodes.KEY_KPPLUS: 0x57,
    ecodes.KEY_KPENTER: 0x58,
    ecodes.KEY_KP1: 0x59, ecodes.KEY_KP2: 0x5A, ecodes.KEY_KP3: 0x5B,
    ecodes.KEY_KP4: 0x5C, ecodes.KEY_KP5: 0x5D, ecodes.KEY_KP6: 0x5E,
    ecodes.KEY_KP7: 0x5F, ecodes.KEY_KP8: 0x60, ecodes.KEY_KP9: 0x61,
    ecodes.KEY_KP0: 0x62,
    ecodes.KEY_KPDOT: 0x63,
}

# Mapeo de botones de raton de Linux (BTN_*) a usage codes USB HID
MOUSE_BUTTON_MAP = {
    ecodes.BTN_LEFT: 0x01,
    ecodes.BTN_RIGHT: 0x02,
    ecodes.BTN_MIDDLE: 0x04,
    ecodes.BTN_SIDE: 0x08,    # boton de retroceso (barra lateral)
    ecodes.BTN_EXTRA: 0x10,   # boton de avance (barra lateral)
}


def _clamp(valor, minimo, maximo):
    return max(minimo, min(maximo, valor))


class KeyboardBridge:
    def __init__(self, device_path='/dev/input/event3', serial_port='/dev/ttyACM0',
                 baudrate=115200, grab=False, toggle_codes=None, toggle_desc='',
                 mouse_path=None, mouse_scale=1.0):
        self.device_path = device_path
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.grab = grab
        self.toggle_codes = toggle_codes or [ecodes.KEY_LEFTCTRL, ecodes.KEY_LEFTALT, ecodes.KEY_B]
        self.toggle_desc = toggle_desc or 'Ctrl+Alt+B'
        self.mouse_path = mouse_path
        self.mouse_scale = mouse_scale
        self.device = None
        self.mouse_dev = None
        self.ser = None
        self.running = False
        self.forwarding = False
        self.pressed = set()
        self.combo_completo = False
        self._dx = 0
        self._dy = 0
        self._wheel = 0

    def connect(self):
        try:
            self.device = InputDevice(self.device_path)
            print(f"Conectado al teclado: {self.device.name}")
            print(f"  Ruta: {self.device_path}")
            print(f"  Fisico: {self.device.phys}")

            capabilities = self.device.capabilities()
            if ecodes.EV_KEY in capabilities:
                print(f"  Teclas soportadas: {len(capabilities[ecodes.EV_KEY])}")

            self.ser = serial.Serial(
                port=self.serial_port,
                baudrate=self.baudrate,
                timeout=0.1,
                write_timeout=0.1,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
            )
            print(f"Conectado al puerto serial: {self.serial_port} @ {self.baudrate} baudios")

            if self.mouse_path:
                self.mouse_dev = InputDevice(self.mouse_path)
                print(f"Conectado al raton: {self.mouse_dev.name}")
                print(f"  Ruta: {self.mouse_path}")
            return True

        except FileNotFoundError:
            print(f"Error: no se encontro el dispositivo {self.device_path}")
            print("  Verifica el teclado y el puerto serial (usa --list-devices)")
            return False
        except PermissionError:
            print("Error: permiso denegado")
            print("  Ejecuta: sudo usermod -a -G input,uucp,dialout $USER")
            print("  Luego reinicia sesion o ejecuta 'newgrp input'")
            return False
        except Exception as e:
            print(f"Error inesperado: {e}")
            return False

    def disconnect(self):
        if self.ser:
            self.ser.close()
        for dev in (self.mouse_dev, self.device):
            if dev and self.forwarding:
                try:
                    dev.ungrab()
                except Exception:
                    pass
        if self.mouse_dev:
            self.mouse_dev.close()
        if self.device:
            self.device.close()
        print("Conexiones cerradas")

    def traducir_tecla(self, keycode):
        hid_code = KEYMAP_LINUX_TO_HID.get(keycode)
        if hid_code is None:
            key_name = ecodes.KEY.get(keycode, f"UNKNOWN_{keycode}")
            print(f"Aviso: tecla no mapeada: {key_name} (0x{keycode:02X})")
        return hid_code

    def enviar_evento(self, *datos):
        try:
            # Los deltas del raton son int8 con signo; convertirlos a bytes
            packet = bytes(int(v) & 0xFF for v in datos)
            self.ser.write(packet)
            self.ser.flush()
        except serial.SerialTimeoutException:
            pass
        except serial.SerialException as e:
            print(f"Error al enviar por serial: {e}")
        except Exception as e:
            print(f"Error inesperado en envio: {e}")

    def _combo_activo(self):
        return set(self.toggle_codes).issubset(self.pressed)

    def _cambiar_estado(self, encendido):
        self.forwarding = encendido
        if encendido:
            for dev in (self.device, self.mouse_dev):
                if dev:
                    try:
                        dev.grab()
                    except Exception as e:
                        print(f"Aviso: no se pudo hacer grab: {e}")
            print(f"[PUENTE ENCENDIDO] teclado y raton enviando al desktop (grab)")
            print(f"  Presiona {self.toggle_desc} para apagar")
        else:
            for dev in (self.device, self.mouse_dev):
                if dev:
                    try:
                        dev.ungrab()
                    except Exception:
                        pass
            print(f"[PUENTE APAGADO] teclado y raton normales de la laptop")
            print(f"  Presiona {self.toggle_desc} para encender")

    def _procesar_tecla(self, event):
        code = event.code

        # Mantener el estado de teclas presionadas
        if event.value == 1:      # presion
            self.pressed.add(code)
        elif event.value == 0:    # soltar
            self.pressed.discard(code)
        else:                     # repeticion: ignorar
            return

        # Detectar el combo de toggle (solo una vez por pulsacion completa)
        if self._combo_activo():
            if not self.combo_completo:
                self.combo_completo = True
                self._cambiar_estado(not self.forwarding)
            return
        if not set(self.toggle_codes).issubset(self.pressed):
            self.combo_completo = False

        # El combo de toggle nunca se reenvia
        if code in self.toggle_codes:
            return

        if not self.forwarding:
            return

        hid_code = self.traducir_tecla(code)
        if hid_code is None:
            return
        if event.value == 1:
            self.enviar_evento(0x01, hid_code)
        else:
            self.enviar_evento(0x00, hid_code)

    def _procesar_mouse(self, event):
        # Acumular deltas relativos hasta el reporte (SYN_REPORT)
        if event.type == ecodes.EV_REL:
            if event.code == ecodes.REL_X:
                self._dx += int(round(event.value * self.mouse_scale))
            elif event.code == ecodes.REL_Y:
                self._dy += int(round(event.value * self.mouse_scale))
            elif event.code == ecodes.REL_WHEEL:
                self._wheel = _clamp(self._wheel + event.value, -127, 127)
            return

        if event.type == ecodes.EV_KEY:
            btn = MOUSE_BUTTON_MAP.get(event.code)
            if btn is None or not self.forwarding:
                return
            if event.value == 1:
                self.enviar_evento(0x03, btn)
            elif event.value == 0:
                self.enviar_evento(0x04, btn)
            return

        if event.type == ecodes.EV_SYN and event.code == ecodes.SYN_REPORT:
            dx = _clamp(self._dx, -127, 127)
            dy = _clamp(self._dy, -127, 127)
            self._dx -= dx
            self._dy -= dy
            if not self.forwarding:
                self._wheel = 0
                return
            if dx or dy or self._wheel:
                self.enviar_evento(0x02, dx, dy, self._wheel)
            self._wheel = 0

    def run(self):
        if not self.device or not self.ser:
            print("No hay conexiones activas")
            return

        self.running = True
        self.forwarding = self.grab

        if self.forwarding:
            self._cambiar_estado(True)
        else:
            print(f"[PUENTE APAGADO] teclado y raton normales de la laptop")
            print(f"  Presiona {self.toggle_desc} para encender y usar el desktop")

        print("Escuchando eventos del teclado y el raton...")

        # Mapear descriptores de fichero a sus dispositivos
        fds = [self.device.fd]
        fd_map = {self.device.fd: self.device}
        if self.mouse_dev:
            fds.append(self.mouse_dev.fd)
            fd_map[self.mouse_dev.fd] = self.mouse_dev

        try:
            while self.running:
                r, _, _ = select.select(fds, [], [], 0.5)
                for fd in r:
                    dev = fd_map[fd]
                    for event in dev.read():
                        if dev is self.mouse_dev:
                            self._procesar_mouse(event)
                        elif event.type == ecodes.EV_KEY:
                            self._procesar_tecla(event)
        except KeyboardInterrupt:
            print("\nInterrupcion recibida")
        except Exception as e:
            print(f"Error en el bucle de eventos: {e}")
        finally:
            self.running = False
            if self.forwarding:
                for dev in (self.mouse_dev, self.device):
                    if dev:
                        try:
                            dev.ungrab()
                            print("Dispositivo liberado")
                        except Exception:
                            pass


def detectar_puerto_serial():
    """Detecta el puerto serial del ESP32 (prefiere el puente UART tipo CH340/CP210x)."""
    from serial.tools import list_ports
    found = []
    for port in list_ports.comports():
        if port.vid is None:
            continue
        vid = int(port.vid)
        if vid in ESP32_SERIAL_VIDS:
            found.append((port, vid))
    if not found:
        return None
    # Preferir el puente USB->UART (CH340/CP210x) sobre el USB nativo del ESP32
    found.sort(key=lambda pv: 1 if pv[1] == 0x303A else 0)
    port, vid = found[0]
    print(f"Puerto serial detectado: {port.device} ({port.description})")
    return port.device


def detectar_teclado():
    """Detecta el teclado fisico de la laptop (excluye ratones y combos inalambricos)."""
    candidatos = []
    for path in sorted(glob.glob('/dev/input/event*')):
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps:
                has_letters = ecodes.KEY_A in caps[ecodes.EV_KEY]
                has_enter = ecodes.KEY_ENTER in caps[ecodes.EV_KEY]
                if has_letters and has_enter:
                    candidatos.append((path, dev.name))
        except Exception:
            pass

    if not candidatos:
        return None

    # Preferir el teclado integrado de la laptop sobre interfaces inalambricas
    def prioridad(item):
        n = item[1].lower()
        if 'wireless' in n or 'yichip' in n or 'logitech' in n:
            return 1
        if 'at translated' in n or 'keyboard' in n:
            return 0
        return 2

    candidatos.sort(key=prioridad)
    mejor = candidatos[0]

    if len(candidatos) == 1 or prioridad(mejor) == 0:
        print(f"Teclado detectado: {mejor[0]} ({mejor[1]})")
        return mejor[0]

    print("Varios teclados encontrados, usa --device para elegir:")
    for path, name in candidatos:
        print(f"  {path}: {name}")
    return None


def detectar_raton():
    """Detecta un raton USB relativo (excluye touchpad, trackpoint, etc.)."""
    candidates = []
    for path in sorted(glob.glob('/dev/input/event*')):
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            rel = set(caps.get(ecodes.EV_REL, []))
            keys = set(caps.get(ecodes.EV_KEY, []))
            if ecodes.REL_X in rel and ecodes.REL_Y in rel and ecodes.BTN_LEFT in keys:
                name = dev.name.lower()
                if any(x in name for x in ('touchpad', 'trackpoint', 'elantech',
                                           'synaptics', 'thinkpad')):
                    continue
                candidates.append((path, dev.name))
        except Exception:
            pass
    if not candidates:
        return None
    if len(candidates) > 1:
        for path, name in candidates:
            if 'logitech' in name.lower():
                print(f"Raton detectado: {path} ({name})")
                return path
    print(f"Raton detectado: {candidates[0][0]} ({candidates[0][1]})")
    return candidates[0][0]


def parse_combo(texto):
    """Convierte 'ctrl+alt+b' en (lista de keycodes evdev, descripcion legible)."""
    nombres = {
        'ctrl': 'KEY_LEFTCTRL', 'alt': 'KEY_LEFTALT', 'shift': 'KEY_LEFTSHIFT',
        'win': 'KEY_LEFTMETA', 'super': 'KEY_LEFTMETA',
    }
    codes, labels = [], []
    for parte in texto.lower().replace(' ', '').split('+'):
        if not parte:
            continue
        clave = nombres.get(parte, f"KEY_{parte.upper()}")
        code = getattr(ecodes, clave, None)
        if code is None:
            raise ValueError(f"Tecla invalida en combo: {parte}")
        codes.append(code)
        labels.append(parte.upper())
    if len(codes) < 2:
        raise ValueError("El combo necesita al menos 2 teclas (ej: ctrl+alt+b)")
    return codes, '+'.join(labels)


def main():
    parser = argparse.ArgumentParser(
        description="Puente USB HID: captura teclado y raton y los envia por UART al ESP32"
    )
    parser.add_argument('-d', '--device', default=None,
                        help='Dispositivo de teclado (ej: /dev/input/event3)')
    parser.add_argument('-m', '--mouse', default=None,
                        help='Dispositivo de raton (ej: /dev/input/event4)')
    parser.add_argument('--no-mouse', action='store_true',
                        help='No usar raton (solo teclado)')
    parser.add_argument('--mouse-scale', type=float, default=1.0,
                        help='Sensibilidad del raton (multiplicador de los deltas, 1.0=normal)')
    parser.add_argument('-s', '--serial', default=None,
                        help='Puerto serial del ESP32 (ej: /dev/ttyACM0)')
    parser.add_argument('-b', '--baudrate', type=int, default=115200,
                        help='Velocidad del puerto serial')
    parser.add_argument('--grab', action='store_true',
                        help='Iniciar ya encendido (solo va al desktop)')
    parser.add_argument('--toggle', default='ctrl+alt+b',
                        help='Combo para encender/apagar el puente (ej: ctrl+alt+b)')
    parser.add_argument('--list-devices', action='store_true',
                        help='Listar todos los dispositivos de entrada disponibles')

    args = parser.parse_args()

    if args.list_devices:
        print("Dispositivos de entrada disponibles:")
        for path in sorted(glob.glob('/dev/input/event*')):
            try:
                dev = InputDevice(path)
                print(f"  {path}: {dev.name}")
            except Exception:
                pass
        return

    device_path = args.device or detectar_teclado()
    serial_port = args.serial or detectar_puerto_serial()

    if not device_path:
        print("No se encontro el teclado, especifica con --device")
        return
    if not serial_port:
        print("No se encontro el puerto serial del ESP32, especifica con --serial")
        return

    mouse_path = None
    if not args.no_mouse:
        mouse_path = args.mouse or detectar_raton()

    try:
        toggle_codes, toggle_desc = parse_combo(args.toggle)
    except ValueError as e:
        print(f"Error en --toggle: {e}")
        return

    bridge = KeyboardBridge(
        device_path=device_path,
        serial_port=serial_port,
        baudrate=args.baudrate,
        grab=args.grab,
        toggle_codes=toggle_codes,
        toggle_desc=toggle_desc,
        mouse_path=mouse_path,
        mouse_scale=args.mouse_scale,
    )

    if bridge.connect():
        try:
            bridge.run()
        finally:
            bridge.disconnect()


if __name__ == "__main__":
    main()
