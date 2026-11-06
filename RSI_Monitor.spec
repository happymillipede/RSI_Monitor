# -*- mode: python ; coding: utf-8 -*-
"""
Receta de PyInstaller para empaquetar RSI Monitor (se corre en cada sistema):

    Windows:  pyinstaller RSI_Monitor.spec   ->  dist\\RSI_Monitor.exe
    macOS:    pyinstaller RSI_Monitor.spec   ->  dist/RSI_Monitor.app

- Sin ventana de consola.
- Código_Bitalino_Python.py y config.ejemplo.json van dentro del paquete. Si junto al
  .exe (o junto a la .app) hay una copia del original, la app usa esa copia: así se
  pueden cambiar umbrales sin volver a empaquetar.

Qué se puede editar aquí:
- UN_SOLO_ARCHIVO (Windows): True = un solo .exe; False = una carpeta con el .exe y
  sus librerías (abre más rápido y el antivirus lo revisa menos). En macOS la .app ya
  es una carpeta, así que siempre se arma así.
- VERSION y los textos de permisos de macOS.
"""

import sys

NOMBRE = "RSI_Monitor"
VERSION = "1.0.0"
ES_MACOS = sys.platform == "darwin"
UN_SOLO_ARCHIVO = not ES_MACOS
ICONO = "recursos/icono.icns" if ES_MACOS else "recursos/icono.ico"

archivos_de_datos = [
    ("Código_Bitalino_Python.py", "."),
    ("config.ejemplo.json", "."),
]

# El original se lee como texto (cargador ast), así que PyInstaller no ve sus imports:
# se agregan a mano. bitalino y la lista de puertos se importan dentro de funciones.
imports_ocultos = ["numpy", "scipy.signal", "bitalino", "serial.tools.list_ports"]

# Lo que no se usa: gráficos y notebook del original, y Bluetooth por dirección MAC
# (la app se conecta por puerto serie).
excluidos = ["matplotlib", "IPython", "tkinter", "bluetooth", "PyQt5", "PyQt6", "PySide2"]

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=archivos_de_datos,
    hiddenimports=imports_ocultos,
    hookspath=[],
    runtime_hooks=[],
    excludes=excluidos,
    noarchive=False,
)
pyz = PYZ(a.pure)

if UN_SOLO_ARCHIVO:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=NOMBRE,
        console=False,
        icon=ICONO,
        upx=False,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=NOMBRE,
        console=False,
        icon=ICONO,
        upx=False,
    )
    coleccion = COLLECT(exe, a.binaries, a.datas, name=NOMBRE, upx=False)

if ES_MACOS:
    app = BUNDLE(
        coleccion,
        name=f"{NOMBRE}.app",
        icon=ICONO,
        bundle_identifier="cl.grupo2.rsimonitor",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "RSI Monitor",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "NSBluetoothAlwaysUsageDescription": (
                "RSI Monitor se conecta por Bluetooth al BITalino para medir la actividad muscular."
            ),
        },
    )
