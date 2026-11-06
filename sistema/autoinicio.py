"""
Iniciar RSI Monitor con el sistema (al iniciar sesión).

- Windows: un valor en el registro, HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
- macOS: el archivo ~/Library/LaunchAgents/cl.grupo2.rsimonitor.plist.
- Linux: no se hace nada (en Linux solo se desarrolla).

La app se abre con --minimizado: queda en la bandeja, con la medición apagada.
Empaquetada (.exe / .app) se aplica sola al abrirla, según config.json. Corriendo
desde el código solo se registra cuando se cambia la opción en los ajustes, para no
dejar "python app.py" en el inicio de sesión de quien desarrolla.

Qué se puede editar aquí: NOMBRE_REGISTRO y ETIQUETA_MACOS.
"""

import importlib
import plistlib
import subprocess
import sys
from pathlib import Path

from nucleo import rutas

NOMBRE_REGISTRO = "RSI_Monitor"
CLAVE_REGISTRO = r"Software\Microsoft\Windows\CurrentVersion\Run"
ETIQUETA_MACOS = "cl.grupo2.rsimonitor"
ARGUMENTO_MINIMIZADO = "--minimizado"


def comando_inicio():
    """Lo que el sistema ejecuta al iniciar sesión."""
    if rutas.esta_empaquetada():
        return [sys.executable, ARGUMENTO_MINIMIZADO]
    python = Path(sys.executable)
    # En Windows, pythonw.exe abre la app sin la ventana negra de la consola.
    pythonw = python.with_name("pythonw.exe")
    if sys.platform == "win32" and pythonw.exists():
        python = pythonw
    return [str(python), str(rutas.RAIZ_PROYECTO / "app.py"), ARGUMENTO_MINIMIZADO]


def valor_registro(comando):
    """Ej.: "C:\\Programas\\RSI_Monitor\\RSI_Monitor.exe" --minimizado"""
    return subprocess.list2cmdline(comando)


def contenido_plist(comando):
    return plistlib.dumps(
        {
            "Label": ETIQUETA_MACOS,
            "ProgramArguments": comando,
            "RunAtLoad": True,
            "ProcessType": "Interactive",
        }
    )


class AutoinicioWindows:
    def __init__(self, winreg=None):
        # winreg solo existe en Windows; las pruebas pasan uno falso.
        self.winreg = winreg or importlib.import_module("winreg")

    def esta_activo(self):
        try:
            with self.winreg.OpenKey(self.winreg.HKEY_CURRENT_USER, CLAVE_REGISTRO) as clave:
                self.winreg.QueryValueEx(clave, NOMBRE_REGISTRO)
            return True
        except FileNotFoundError:
            return False

    def activar(self, comando):
        with self.winreg.CreateKey(self.winreg.HKEY_CURRENT_USER, CLAVE_REGISTRO) as clave:
            self.winreg.SetValueEx(clave, NOMBRE_REGISTRO, 0, self.winreg.REG_SZ, valor_registro(comando))

    def desactivar(self):
        try:
            with self.winreg.OpenKey(
                self.winreg.HKEY_CURRENT_USER, CLAVE_REGISTRO, 0, self.winreg.KEY_SET_VALUE
            ) as clave:
                self.winreg.DeleteValue(clave, NOMBRE_REGISTRO)
        except FileNotFoundError:
            pass


class AutoinicioMacOS:
    def __init__(self, carpeta_usuario=None):
        carpeta_usuario = Path(carpeta_usuario or Path.home())
        self.ruta = carpeta_usuario / "Library" / "LaunchAgents" / f"{ETIQUETA_MACOS}.plist"

    def esta_activo(self):
        return self.ruta.exists()

    def activar(self, comando):
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_bytes(contenido_plist(comando))

    def desactivar(self):
        self.ruta.unlink(missing_ok=True)


def crear_autoinicio(sistema=sys.platform):
    """El autoinicio de este sistema, o None si no se puede (Linux)."""
    if sistema == "win32":
        return AutoinicioWindows()
    if sistema == "darwin":
        return AutoinicioMacOS()
    return None


def soportado(sistema=sys.platform):
    return sistema in ("win32", "darwin")


def aplicar(activar, autoinicio=None, comando=None):
    """
    Deja el inicio automático como se pide. Devuelve False si este sistema no lo permite.
    Puede lanzar OSError si el sistema no deja escribir el registro o el archivo.
    """
    autoinicio = autoinicio or crear_autoinicio()
    if autoinicio is None:
        return False
    if activar:
        autoinicio.activar(comando or comando_inicio())
    else:
        autoinicio.desactivar()
    return True
