"""
Crea los accesos directos "RSI Monitor" en el Escritorio y en el menú Inicio (Windows).

Lo ejecuta instalar.bat con el Python de .venv:
    .venv\\Scripts\\python.exe herramientas\\crear_accesos_directos.py

El acceso abre app.py con pythonw.exe (sin la ventana negra de la consola) y con el
ícono de recursos/icono.ico. Python no trae cómo crear un acceso directo de Windows,
así que se lo pide a PowerShell. Las rutas van en variables de entorno, para no tener
que escaparlas.

Qué se puede editar aquí: NOMBRE_ACCESO y DESCRIPCION.
"""

import os
import subprocess
import sys
from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
NOMBRE_ACCESO = "RSI Monitor"
DESCRIPCION = "Detector de fatiga muscular con BITalino"

COMANDO_POWERSHELL = (
    "$shell = New-Object -ComObject WScript.Shell; "
    "foreach ($carpeta in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) { "
    "$ruta = Join-Path $carpeta ($env:RSI_NOMBRE + '.lnk'); "
    "$acceso = $shell.CreateShortcut($ruta); "
    "$acceso.TargetPath = $env:RSI_PROGRAMA; "
    "$acceso.Arguments = $env:RSI_ARGUMENTOS; "
    "$acceso.WorkingDirectory = $env:RSI_CARPETA; "
    "$acceso.IconLocation = $env:RSI_ICONO; "
    "$acceso.Description = $env:RSI_DESCRIPCION; "
    "$acceso.Save(); "
    "Write-Output $ruta }"
)


def variables_acceso(raiz=RAIZ_PROYECTO, python=sys.executable):
    """Lo que necesita COMANDO_POWERSHELL, como variables de entorno."""
    raiz = Path(raiz)
    return {
        "RSI_NOMBRE": NOMBRE_ACCESO,
        "RSI_PROGRAMA": str(Path(python).with_name("pythonw.exe")),
        "RSI_ARGUMENTOS": subprocess.list2cmdline([str(raiz / "app.py")]),
        "RSI_CARPETA": str(raiz),
        "RSI_ICONO": f"{raiz / 'recursos' / 'icono.ico'},0",
        "RSI_DESCRIPCION": DESCRIPCION,
    }


def crear(ejecutar=subprocess.run):
    """Crea los dos accesos. Devuelve el resultado de PowerShell."""
    return ejecutar(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", COMANDO_POWERSHELL],
        env={**os.environ, **variables_acceso()},
        capture_output=True,
        text=True,
        errors="replace",
    )


def principal():
    if sys.platform != "win32":
        print("Los accesos directos solo se crean en Windows.")
        return 0
    resultado = crear()
    for ruta in resultado.stdout.splitlines():
        if ruta.strip():
            print(f"Acceso directo: {ruta.strip()}")
    if resultado.returncode != 0:
        print(resultado.stderr.strip())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(principal())
