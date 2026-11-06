"""Instalador de Windows: formato de instalar.bat, lo que ejecuta y los accesos directos."""

import importlib.util
import re
import subprocess

import pytest

from nucleo import rutas

BAT = rutas.RAIZ_PROYECTO / "instalar.bat"
SCRIPT_ACCESOS = rutas.RAIZ_PROYECTO / "herramientas" / "crear_accesos_directos.py"


def texto_bat():
    return BAT.read_bytes().decode("ascii")


def cargar_accesos():
    especificacion = importlib.util.spec_from_file_location("crear_accesos_directos", SCRIPT_ACCESOS)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def test_bat_es_ascii_con_crlf():
    contenido = BAT.read_bytes()
    contenido.decode("ascii")
    assert contenido.count(b"\n") == contenido.count(b"\r\n")


def test_bat_no_usa_powershell_ni_descarga_programas():
    # Lo que hacía que el antivirus lo confundiera con un virus.
    texto = texto_bat().lower()
    for sospechoso in ("powershell", "executionpolicy", "curl", "bitsadmin", "invoke-webrequest", "currentversion\\run"):
        assert sospechoso not in texto


def test_bat_usa_archivos_que_existen():
    texto = texto_bat()
    assert "requirements.txt" in texto
    assert r"herramientas\crear_accesos_directos.py" in texto
    assert SCRIPT_ACCESOS.exists()


def test_version_de_python_coincide_con_requirements():
    requisitos = (rutas.RAIZ_PROYECTO / "requirements.txt").read_text(encoding="utf-8")
    assert "Python 3.10" in requisitos
    assert "--id Python.Python.3.10 " in texto_bat()


def test_codigo_version_acepta_este_python():
    codigo = re.search(r'^set "CODIGO_VERSION=(.*)"\r$', texto_bat(), re.MULTILINE).group(1)
    assert "%" not in codigo and '"' not in codigo
    with pytest.raises(SystemExit) as salida:
        exec(codigo)
    assert salida.value.code == 0


def test_comprueba_las_dependencias_de_requirements():
    linea = re.search(r'-c "import ([^"]+)"', texto_bat()).group(1)
    for modulo in linea.split(", "):
        __import__(modulo)


def test_variables_del_acceso(tmp_path):
    accesos = cargar_accesos()
    raiz = tmp_path / "Mis cosas" / "RSI_Monitor"
    variables = accesos.variables_acceso(raiz, raiz / ".venv" / "Scripts" / "python.exe")
    assert variables["RSI_PROGRAMA"] == str(raiz / ".venv" / "Scripts" / "pythonw.exe")
    assert variables["RSI_ARGUMENTOS"] == f'"{raiz / "app.py"}"'
    assert variables["RSI_CARPETA"] == str(raiz)
    assert variables["RSI_ICONO"].endswith("icono.ico,0")
    assert (rutas.RAIZ_PROYECTO / "recursos" / "icono.ico").exists()


def test_comando_powershell_usa_todas_las_variables():
    accesos = cargar_accesos()
    # Sin comillas dobles: así llega entero como un solo argumento a PowerShell.
    assert '"' not in accesos.COMANDO_POWERSHELL
    usadas = set(re.findall(r"\$env:(RSI_\w+)", accesos.COMANDO_POWERSHELL))
    assert usadas == set(accesos.variables_acceso())


def test_crear_pasa_las_rutas_en_el_entorno():
    accesos = cargar_accesos()
    llamadas = []

    def ejecutar(comando, **opciones):
        llamadas.append((comando, opciones))
        return subprocess.CompletedProcess(comando, 0, "", "")

    accesos.crear(ejecutar)
    comando, opciones = llamadas[0]
    assert comando[0] == "powershell" and comando[-1] == accesos.COMANDO_POWERSHELL
    assert "-ExecutionPolicy" not in comando
    assert opciones["env"]["RSI_CARPETA"] == str(accesos.RAIZ_PROYECTO)
