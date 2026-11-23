"""
generar_exe.py: crea el programa para usar RSI Monitor sin instalar Python.

    python generar_exe.py

- En Windows crea dist\\RSI_Monitor.exe (un solo archivo).
- En macOS crea dist/RSI_Monitor.app.
Hay que ejecutarlo en cada sistema. Crea su propio entorno (.venv_exe), instala las
dependencias y PyInstaller (necesita Internet la primera vez) y empaqueta app.py con
la carpeta interfaz/.

Qué se puede editar aquí: NOMBRE y VERSION_PYINSTALLER.
"""

import subprocess
import sys
from pathlib import Path

NOMBRE = "RSI_Monitor"
VERSION_PYINSTALLER = "6.22.3"
CARPETA = Path(__file__).resolve().parent
ARCHIVOS_NECESARIOS = ("requirements.txt", "app.py", "configuracion.py", "procesamiento.py", "fatiga.py",
                       "calibracion.py", "grabacion.py", "conexion.py", "interfaz/index.html")


def principal():
    if sys.platform not in ("win32", "darwin"):
        raise RuntimeError("Ejecuta este script en Windows (para el .exe) o en macOS (para la .app).")
    if not (3, 10) <= sys.version_info[:2] < (3, 14):
        raise RuntimeError("Usa Python 3.10 a 3.13; se recomienda Python 3.10.11.")
    for nombre in ARCHIVOS_NECESARIOS:
        if not (CARPETA / nombre).is_file():
            raise RuntimeError(f"Falta {nombre}. Descarga la carpeta completa del proyecto.")

    entorno = CARPETA / ".venv_exe"
    python = entorno / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        print("1/3 Creando el entorno de compilación…", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(entorno)], check=True)
    else:
        print("1/3 Usando el entorno de compilación existente.", flush=True)

    print("2/3 Instalando dependencias (la primera vez necesita Internet)…", flush=True)
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
                    "-r", "requirements.txt", f"pyinstaller=={VERSION_PYINSTALLER}"], cwd=CARPETA, check=True)

    print(f"3/3 Generando {NOMBRE}…", flush=True)
    comando = [str(python), "-m", "PyInstaller", "--noconfirm", "--windowed", "--name", NOMBRE,
               "--collect-all", "webview", "--add-data", "interfaz:interfaz"]
    # En Windows, un solo .exe. En macOS, la .app (PyInstaller no recomienda --onefile ahí).
    if sys.platform == "win32":
        comando.append("--onefile")
    comando.append("app.py")
    subprocess.run(comando, cwd=CARPETA, check=True)

    resultado = CARPETA / "dist" / (f"{NOMBRE}.exe" if sys.platform == "win32" else f"{NOMBRE}.app")
    if not resultado.exists():
        raise RuntimeError(f"La compilación terminó pero no se encontró {resultado.name}.")
    print(f"\nListo. El programa quedó en:\n{resultado}", flush=True)


if __name__ == "__main__":
    try:
        principal()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"\nNo se pudo generar el programa: {error}", file=sys.stderr)
        sys.exit(1)
