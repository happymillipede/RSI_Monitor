"""
iniciar.py: instala lo necesario (la primera vez) y abre RSI Monitor.

    python iniciar.py             abre la app
    python iniciar.py --simular   abre la app proponiendo la simulación

La primera vez crea el entorno .venv e instala requirements.txt (necesita Internet).
Las veces siguientes solo abre la app.

Qué se puede editar aquí: VERSION_PYTHON.
"""

import subprocess
import sys
from pathlib import Path

VERSION_PYTHON = (3, 10)  # la del notebook del grupo (Python 3.10.11)
RAIZ = Path(__file__).resolve().parent
ENTORNO = RAIZ / ".venv"
PYTHON = ENTORNO / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
MARCA_INSTALADO = ENTORNO / ".rsi_instalado"


def instalar():
    if sys.version_info[:2] != VERSION_PYTHON:
        print(f"Aviso: este Python es {sys.version.split()[0]}; el grupo usa 3.10.11.")
    if not PYTHON.exists():
        print("Creando el entorno .venv…", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(ENTORNO)], check=True)
    print("Instalando las dependencias (la primera vez demora unos minutos)…", flush=True)
    subprocess.run([str(PYTHON), "-m", "ensurepip", "--upgrade"], check=False, capture_output=True)
    subprocess.run([str(PYTHON), "-m", "pip", "install", "--disable-pip-version-check",
                    "-r", str(RAIZ / "requirements.txt")], check=True)
    if sys.platform.startswith("linux"):
        subprocess.run([str(PYTHON), "-m", "pip", "install", "pywebview[qt]"], check=True)
    MARCA_INSTALADO.write_text("ok\n", encoding="utf-8")


def principal():
    if not MARCA_INSTALADO.exists():
        instalar()
    return subprocess.run([str(PYTHON), str(RAIZ / "app.py"), *sys.argv[1:]], cwd=RAIZ).returncode


if __name__ == "__main__":
    try:
        sys.exit(principal())
    except subprocess.CalledProcessError as error:
        print(f"\nNo se pudo instalar o abrir la app: {error}", file=sys.stderr)
        sys.exit(1)
