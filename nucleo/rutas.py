"""
Rutas de la aplicación: dónde se guardan config.json y datos/, y dónde se busca
el código original (Código_Bitalino_Python.py).

Reglas:
- config.json y datos/ van junto al ejecutable (o junto a app.py si se corre desde
  el código). Si ahí no se puede escribir, van a la carpeta de datos del usuario:
  %APPDATA%\\RSI_Monitor en Windows y ~/Library/Application Support/RSI_Monitor en macOS.
- En macOS, con la app empaquetada (.app) siempre se usa Application Support,
  porque escribir dentro o junto al .app rompe su firma.
- El original se busca primero junto al ejecutable (para poder editarlo sin
  recompilar), después en la raíz del proyecto y al final dentro del ejecutable.

Qué se puede editar aquí: los nombres de archivos y carpetas de abajo.
"""

import os
import sys
import unicodedata
from pathlib import Path

NOMBRE_APP = "RSI_Monitor"
NOMBRE_ORIGINAL = "Código_Bitalino_Python.py"
NOMBRE_CONFIG = "config.json"
NOMBRE_CONFIG_EJEMPLO = "config.ejemplo.json"
NOMBRE_CARPETA_DATOS = "datos"

# Carpeta donde están app.py, nucleo/, ui/, etc.
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent


def esta_empaquetada():
    """True si la app corre como ejecutable de PyInstaller (.exe o .app)."""
    return getattr(sys, "frozen", False)


def carpeta_ejecutable():
    """Carpeta del .exe, carpeta que contiene el .app, o la raíz del proyecto en desarrollo."""
    if not esta_empaquetada():
        return RAIZ_PROYECTO

    ejecutable = Path(sys.executable).resolve()
    # En macOS el ejecutable está en RSI_Monitor.app/Contents/MacOS/
    for carpeta in ejecutable.parents:
        if carpeta.suffix == ".app":
            return carpeta.parent
    return ejecutable.parent


def carpeta_recursos():
    """Carpeta con los archivos incluidos en el ejecutable (PyInstaller usa sys._MEIPASS)."""
    return Path(getattr(sys, "_MEIPASS", RAIZ_PROYECTO))


def carpeta_datos_usuario():
    """Carpeta de datos del usuario según el sistema operativo."""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / NOMBRE_APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / NOMBRE_APP
    return Path.home() / ".local" / "share" / NOMBRE_APP


def se_puede_escribir(carpeta):
    """Prueba crear y borrar un archivo en la carpeta."""
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        prueba = carpeta / ".prueba_escritura"
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink()
        return True
    except OSError:
        return False


def carpeta_base():
    """Carpeta donde van config.json y datos/."""
    if esta_empaquetada() and sys.platform == "darwin":
        return carpeta_datos_usuario()

    junto_al_ejecutable = carpeta_ejecutable()
    if se_puede_escribir(junto_al_ejecutable):
        return junto_al_ejecutable
    return carpeta_datos_usuario()


def carpeta_datos(base):
    """Carpeta datos/ dentro de la carpeta base (se crea si no existe)."""
    carpeta = Path(base) / NOMBRE_CARPETA_DATOS
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def buscar_archivo(carpeta, nombre):
    """
    Busca 'nombre' dentro de 'carpeta'. Compara los nombres normalizados (NFC)
    porque macOS puede guardar la "ó" de "Código" como dos caracteres (NFD).
    """
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return None

    buscado = unicodedata.normalize("NFC", nombre)
    for ruta in carpeta.iterdir():
        if unicodedata.normalize("NFC", ruta.name) == buscado:
            return ruta
    return None


def buscar_original():
    """Ruta del código original, en el orden de búsqueda explicado arriba."""
    for carpeta in (carpeta_ejecutable(), RAIZ_PROYECTO, carpeta_recursos()):
        ruta = buscar_archivo(carpeta, NOMBRE_ORIGINAL)
        if ruta is not None:
            return ruta

    raise FileNotFoundError(
        f"No se encontró {NOMBRE_ORIGINAL} junto al ejecutable ni en el proyecto."
    )
