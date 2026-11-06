"""
compilar.py: deja RSI Monitor funcionando en este computador (macOS, Windows o Linux).

Uso (desde la carpeta RSI_Monitor):
    python compilar.py              hace todo: verificar, instalar, compilar, probar e iniciar
    python compilar.py verificar    1. revisa Python 3.10 (y Node.js y npm, si están)
    python compilar.py instalar     2. entorno virtual (.venv) + backend/requirements.txt
    python compilar.py compilar     3-4. npm ci, npm run build y copia el frontend a backend/estaticos/
    python compilar.py probar       5. pytest (y tsc --noEmit y eslint, si está Node.js)
    python compilar.py iniciar      6. levanta la app en segundo plano y abre el navegador
    python compilar.py detener      7. detiene la app
    python compilar.py docker       8. (opcional) imagen Docker en modo simulación

Node.js NO hace falta para usar la app: la página ya compilada está guardada en git
(backend/estaticos/). Solo hace falta para cambiar la página (carpeta frontend/): en ese
caso, después de cambiarla, corran "python compilar.py compilar" y hagan commit de
backend/estaticos/ para que los demás reciban la página nueva.

Para usar el BITalino real, la app tiene que correr así (nativa), no en Docker:
Docker no puede usar el Bluetooth del computador.

Qué se puede editar aquí: la configuración de abajo.
"""

import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

# --- Configuración ---
PUERTO = 8000  # puerto de la app: http://localhost:PUERTO
SIMULACION_POR_DEFECTO = True  # True: el botón Encender propone la simulación (útil sin BITalino)
VERSION_PYTHON = (3, 10)  # la del código original: Python 3.10.11
VERSION_MINIMA_NODE = (20, 9)  # la mínima que pide Next.js 16
ESPERA_INICIO_S = 30  # cuánto se espera a que la app responda al iniciarla
ESPERA_DETENER_S = 10  # cuánto se espera a que la app se cierre sola antes de forzarla
NOMBRE_DOCKER = "rsi-monitor"  # nombre de la imagen, del contenedor y (con "-datos") del volumen

# --- Rutas ---
RAIZ = Path(__file__).resolve().parent
BACKEND = RAIZ / "backend"
FRONTEND = RAIZ / "frontend"
ENTORNO = RAIZ / ".venv"
ESTATICOS = BACKEND / "estaticos"
DATOS = RAIZ / "datos"
ARCHIVO_PID = DATOS / "servidor.pid"
ARCHIVO_LOG = DATOS / "servidor.log"
EN_WINDOWS = sys.platform == "win32"


class ErrorPaso(Exception):
    """Un paso no se pudo hacer. El mensaje dice qué instalar o revisar."""


def titulo(texto):
    print(f"\n=== {texto} ===", flush=True)


def ejecutar(comando, carpeta=RAIZ):
    """Corre un comando mostrando su salida. Si falla, detiene el script."""
    print("$", " ".join(str(parte) for parte in comando), flush=True)
    resultado = subprocess.run([str(parte) for parte in comando], cwd=carpeta)
    if resultado.returncode != 0:
        raise ErrorPaso(f"El comando terminó con error (código {resultado.returncode}).")


def salida_de(comando):
    """Corre un comando y devuelve lo que imprime, o None si no existe o falla."""
    try:
        return subprocess.run(comando, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def python_del_entorno():
    carpeta = "Scripts" if EN_WINDOWS else "bin"
    return ENTORNO / carpeta / ("python.exe" if EN_WINDOWS else "python")


def comando_npm():
    """npm, o None si no está instalado (en Windows encuentra npm.cmd)."""
    return shutil.which("npm")


def hay_pagina_compilada():
    return (ESTATICOS / "index.html").exists()


def node_suficiente():
    """None si Node.js y npm sirven para compilar; si no, el motivo."""
    version_node = salida_de([shutil.which("node") or "node", "--version"])
    if version_node is None:
        return "no está instalado"
    numeros = tuple(int(n) for n in version_node.lstrip("v").split(".")[:2])
    if numeros < VERSION_MINIMA_NODE:
        return f"Node.js {version_node} es muy antiguo"
    if comando_npm() is None:
        return "falta npm"
    return None


# --- 1. Verificar requisitos ---


def buscar_python_310():
    """Un comando que ejecute Python 3.10 (este mismo, py -3.10 o python3.10)."""
    if sys.version_info[:2] == VERSION_PYTHON:
        return [sys.executable]
    texto = ".".join(map(str, VERSION_PYTHON))
    candidatos = [["py", f"-{texto}"]] if EN_WINDOWS else [[f"python{texto}"]]
    for candidato in candidatos:
        version = salida_de(candidato + ["-c", "import sys; print(sys.version_info[:2])"])
        if version == str(VERSION_PYTHON):
            return candidato
    return None


def verificar():
    titulo("1. Verificar requisitos")
    problemas = []

    if python_del_entorno().exists():
        print(f"Python: se usará el entorno {ENTORNO.name}/ que ya existe.")
    elif buscar_python_310():
        print(f"Python {VERSION_PYTHON[0]}.{VERSION_PYTHON[1]}: encontrado.")
    else:
        problemas.append(
            "Falta Python 3.10.11. Instálenlo desde https://www.python.org/downloads/release/python-31011/ "
            "(en macOS también sirve: pyenv install 3.10.11)."
        )

    motivo = node_suficiente()
    if motivo is None:
        print("Node.js y npm: bien (se puede compilar la página).")
    elif hay_pagina_compilada():
        print(f"Node.js: {motivo}. No importa: se usa la página ya compilada (backend/estaticos/).")
    else:
        problemas.append(
            f"Falta la página compilada (backend/estaticos/) y {motivo} para compilarla. "
            "Bajen de nuevo el repositorio (git pull) o instalen Node.js LTS desde https://nodejs.org"
        )

    if problemas:
        raise ErrorPaso("\n".join("- " + problema for problema in problemas))


# --- 2. Entorno virtual del backend ---


def instalar():
    titulo("2. Entorno virtual del backend")
    python = python_del_entorno()
    if not python.exists():
        base = buscar_python_310()
        if base is None:
            raise ErrorPaso("Falta Python 3.10.11 (ver el paso 1).")
        ejecutar(base + ["-m", "venv", ENTORNO])
    if salida_de([str(python), "-m", "pip", "--version"]) is None:
        ejecutar([python, "-m", "ensurepip", "--upgrade"])  # entornos creados sin pip (ej. con uv)
    ejecutar([python, "-m", "pip", "install", "-r", BACKEND / "requirements.txt"])


# --- 3 y 4. Frontend ---


def compilar(obligatorio=True):
    titulo("3. Compilar el frontend")
    motivo = node_suficiente()
    if motivo is not None:
        if obligatorio or not hay_pagina_compilada():
            raise ErrorPaso(f"Para compilar la página hace falta Node.js LTS ({motivo}): https://nodejs.org")
        print(f"Se omite ({motivo}): se usa la página ya compilada que viene en el repositorio.")
        return
    npm = comando_npm()
    ejecutar([npm, "ci"], FRONTEND)
    ejecutar([npm, "run", "build"], FRONTEND)

    titulo("4. Copiar el frontend a backend/estaticos/")
    shutil.rmtree(ESTATICOS, ignore_errors=True)
    shutil.copytree(FRONTEND / "out", ESTATICOS)
    print(f"Listo: {ESTATICOS}")


# --- 5. Pruebas ---


def probar():
    titulo("5. Pruebas")
    ejecutar([python_del_entorno(), "-m", "pytest", "-q"], BACKEND)
    motivo = node_suficiente()
    if motivo is not None:
        print(f"Se omiten tsc y eslint del frontend ({motivo}).")
        return
    npm = comando_npm()
    ejecutar([npm, "run", "tipos"], FRONTEND)
    ejecutar([npm, "run", "lint"], FRONTEND)


# --- 6. Iniciar la app ---


def url_app():
    return f"http://localhost:{PUERTO}"


def responde():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/api/estado", timeout=1):
            return True
    except OSError:
        return False


def iniciar():
    titulo("6. Iniciar la app")
    if responde():
        print(f"La app ya está corriendo en {url_app()}")
        webbrowser.open(url_app())
        return

    comando = [str(python_del_entorno()), "-m", "app.main", "--puerto", str(PUERTO)]
    if SIMULACION_POR_DEFECTO:
        comando.append("--sim")
    DATOS.mkdir(exist_ok=True)
    # En segundo plano y separada de esta terminal: el script termina y la app sigue.
    separar = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if EN_WINDOWS else {"start_new_session": True}
    with open(ARCHIVO_LOG, "w", encoding="utf-8") as log:
        proceso = subprocess.Popen(comando, cwd=BACKEND, stdout=log, stderr=subprocess.STDOUT, **separar)
    ARCHIVO_PID.write_text(str(proceso.pid), encoding="utf-8")

    fin = time.monotonic() + ESPERA_INICIO_S
    while not responde():
        if proceso.poll() is not None or time.monotonic() > fin:
            raise ErrorPaso(f"La app no arrancó. Revisen {ARCHIVO_LOG}")
        time.sleep(0.5)
    print(f"RSI Monitor está corriendo en {url_app()} (proceso {proceso.pid}).")
    print("Para detenerla: python compilar.py detener")
    webbrowser.open(url_app())


# --- 7. Detener la app ---


def proceso_vivo(pid):
    if EN_WINDOWS:
        return str(pid) in (salida_de(["tasklist", "/FI", f"PID eq {pid}", "/NH"]) or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def detener():
    titulo("7. Detener la app")
    if not ARCHIVO_PID.exists():
        print("No hay una app iniciada con este script.")
        return
    pid = int(ARCHIVO_PID.read_text(encoding="utf-8"))
    if proceso_vivo(pid):
        # Primero se le pide que se cierre sola: así guarda el reloj y el descanso.
        os.kill(pid, signal.CTRL_BREAK_EVENT if EN_WINDOWS else signal.SIGTERM)
        fin = time.monotonic() + ESPERA_DETENER_S
        while proceso_vivo(pid) and time.monotonic() < fin:
            time.sleep(0.3)
        if proceso_vivo(pid):
            if EN_WINDOWS:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
            else:
                os.kill(pid, signal.SIGKILL)
    ARCHIVO_PID.unlink()
    print("La app se detuvo.")


# --- 8. Docker (opcional) ---


def docker():
    titulo("8. Docker (solo simulación)")
    print(
        "Ojo: Docker no puede usar el Bluetooth del computador. Dentro de Docker solo\n"
        "funciona la simulación. Para el BITalino real usen: python compilar.py iniciar"
    )
    if shutil.which("docker") is None:
        raise ErrorPaso("No se encontró Docker. Instalen Docker Desktop desde https://www.docker.com")
    ejecutar(["docker", "build", "-t", NOMBRE_DOCKER, "."])
    subprocess.run(["docker", "rm", "-f", NOMBRE_DOCKER], capture_output=True)
    ejecutar([
        "docker", "run", "-d", "--name", NOMBRE_DOCKER,
        "-p", f"127.0.0.1:{PUERTO}:{PUERTO}",  # solo accesible desde este computador
        "-v", f"{NOMBRE_DOCKER}-datos:/app/datos",  # los datos sobreviven al contenedor
        NOMBRE_DOCKER,
        "python", "-m", "app.main", "--host", "0.0.0.0", "--puerto", str(PUERTO), "--sim",
    ])
    print(f"Listo: {url_app()}  (para detenerla: docker stop {NOMBRE_DOCKER})")


PASOS = {
    "verificar": [verificar],
    "instalar": [instalar],
    "compilar": [compilar],
    "probar": [probar],
    "iniciar": [iniciar],
    "detener": [detener],
    "docker": [docker],
    # Con "todo", compilar la página es opcional: sin Node.js se usa la que viene en git.
    "todo": [verificar, instalar, lambda: compilar(obligatorio=False), probar, iniciar],
}


def principal():
    nombre = sys.argv[1] if len(sys.argv) > 1 else "todo"
    if nombre not in PASOS:
        print(__doc__)
        return 1
    try:
        for paso in PASOS[nombre]:
            paso()
    except ErrorPaso as error:
        print(f"\nNo se pudo terminar:\n{error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(principal())
