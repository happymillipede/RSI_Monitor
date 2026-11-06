"""Inicio con el sistema: registro de Windows y LaunchAgent de macOS (con imitaciones)."""

import plistlib
import sys

from nucleo import rutas
from sistema import autoinicio
from sistema.autoinicio import (
    ARGUMENTO_MINIMIZADO,
    CLAVE_REGISTRO,
    ETIQUETA_MACOS,
    NOMBRE_REGISTRO,
    AutoinicioMacOS,
    AutoinicioWindows,
)


class ClaveFalsa:
    def __init__(self, registro, ruta):
        self.registro = registro
        self.ruta = ruta

    def __enter__(self):
        return self

    def __exit__(self, *errores):
        return False


class WinregFalso:
    """Imita lo que se usa del módulo winreg, guardando los valores en un diccionario."""

    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.valores = {}  # (ruta, nombre) -> (tipo, valor)
        self.claves = set()

    def CreateKey(self, raiz, ruta):
        self.claves.add((raiz, ruta))
        return ClaveFalsa(self, (raiz, ruta))

    def OpenKey(self, raiz, ruta, reservado=0, acceso=0):
        if (raiz, ruta) not in self.claves:
            raise FileNotFoundError(ruta)
        return ClaveFalsa(self, (raiz, ruta))

    def SetValueEx(self, clave, nombre, reservado, tipo, valor):
        self.valores[(clave.ruta, nombre)] = (tipo, valor)

    def QueryValueEx(self, clave, nombre):
        if (clave.ruta, nombre) not in self.valores:
            raise FileNotFoundError(nombre)
        tipo, valor = self.valores[(clave.ruta, nombre)]
        return valor, tipo

    def DeleteValue(self, clave, nombre):
        if (clave.ruta, nombre) not in self.valores:
            raise FileNotFoundError(nombre)
        del self.valores[(clave.ruta, nombre)]


def test_windows_registra_y_borra_el_valor_run():
    winreg = WinregFalso()
    windows = AutoinicioWindows(winreg)
    assert not windows.esta_activo()

    comando = [r"C:\Program Files\RSI Monitor\RSI_Monitor.exe", ARGUMENTO_MINIMIZADO]
    assert autoinicio.aplicar(True, windows, comando)
    assert windows.esta_activo()
    tipo, valor = winreg.valores[(("HKCU", CLAVE_REGISTRO), NOMBRE_REGISTRO)]
    assert tipo == winreg.REG_SZ
    assert valor == '"C:\\Program Files\\RSI Monitor\\RSI_Monitor.exe" --minimizado'

    autoinicio.aplicar(False, windows)
    assert not windows.esta_activo()
    autoinicio.aplicar(False, windows)  # desactivar dos veces no falla


def test_macos_escribe_y_borra_el_launch_agent(tmp_path):
    macos = AutoinicioMacOS(tmp_path)
    comando = ["/Applications/RSI_Monitor.app/Contents/MacOS/RSI_Monitor", ARGUMENTO_MINIMIZADO]
    autoinicio.aplicar(True, macos, comando)

    ruta = tmp_path / "Library" / "LaunchAgents" / f"{ETIQUETA_MACOS}.plist"
    assert macos.esta_activo() and ruta.exists()
    contenido = plistlib.loads(ruta.read_bytes())
    assert contenido["Label"] == ETIQUETA_MACOS
    assert contenido["ProgramArguments"] == comando
    assert contenido["RunAtLoad"] is True

    autoinicio.aplicar(False, macos)
    assert not ruta.exists()


def test_linux_no_hace_nada():
    assert autoinicio.crear_autoinicio("linux") is None
    assert not autoinicio.soportado("linux")
    assert autoinicio.soportado("win32") and autoinicio.soportado("darwin")


def test_comando_empaquetada_y_desde_el_codigo(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/ruta/RSI_Monitor.exe")
    assert autoinicio.comando_inicio() == ["/ruta/RSI_Monitor.exe", ARGUMENTO_MINIMIZADO]

    monkeypatch.delattr(sys, "frozen")
    comando = autoinicio.comando_inicio()
    assert comando[1] == str(rutas.RAIZ_PROYECTO / "app.py")
    assert comando[-1] == ARGUMENTO_MINIMIZADO
