"""Instalador de Windows: formato de los archivos y el código Python que ejecuta."""

import re

import pytest

from nucleo import rutas
from sistema import autoinicio

BAT = rutas.RAIZ_PROYECTO / "instalar.bat"
PS1 = rutas.RAIZ_PROYECTO / "instalar.ps1"


def texto_ps1():
    return PS1.read_bytes().decode("utf-8-sig")


def constante_ps1(nombre):
    """El valor de una constante de instalar.ps1 escrita como $NOMBRE = "..." o '...'."""
    coincidencia = re.search(rf"^\${nombre} = (['\"])(.*)\1\r?$", texto_ps1(), re.MULTILINE)
    assert coincidencia, nombre
    return coincidencia.group(2)


def test_bat_es_ascii_con_crlf_y_llama_al_ps1():
    contenido = BAT.read_bytes()
    contenido.decode("ascii")
    assert contenido.count(b"\n") == contenido.count(b"\r\n")
    assert b'-File "%~dp0instalar.ps1"' in contenido


def test_ps1_tiene_bom_y_crlf():
    # Windows PowerShell 5 lee como ANSI un .ps1 sin BOM y rompe las tildes.
    contenido = PS1.read_bytes()
    assert contenido.startswith(b"\xef\xbb\xbf")
    assert contenido.count(b"\n") == contenido.count(b"\r\n")


def test_version_de_python_coincide_con_requirements():
    version = constante_ps1("VERSION_PYTHON")
    requisitos = (rutas.RAIZ_PROYECTO / "requirements.txt").read_text(encoding="utf-8")
    assert f"Python {version}" in requisitos
    assert re.fullmatch(r"[0-9A-F]{64}", constante_ps1("SHA256_PYTHON"))


@pytest.mark.parametrize("nombre", ["CODIGO_VERSION", "CODIGO_AUTOINICIO"])
def test_codigo_python_sin_comillas_dobles_ni_variables(nombre):
    # Va entre comillas dobles de PowerShell: un $ se reemplazaría, y PowerShell 5
    # corta los argumentos que llevan comillas dobles adentro.
    codigo = constante_ps1(nombre)
    assert "$" not in codigo and "`" not in codigo and '"' not in codigo


def test_codigo_version_acepta_este_python():
    with pytest.raises(SystemExit) as salida:
        exec(constante_ps1("CODIGO_VERSION"))
    assert salida.value.code == 0


def test_codigo_autoinicio_usa_config_json(tmp_path, monkeypatch, capsys):
    pedidos = []
    monkeypatch.setattr(rutas, "carpeta_base", lambda: tmp_path)
    monkeypatch.setattr(autoinicio, "aplicar", lambda activar: pedidos.append(activar))
    exec(constante_ps1("CODIGO_AUTOINICIO"))
    assert pedidos == [True]
    assert capsys.readouterr().out.strip() == "activado"
    assert (tmp_path / rutas.NOMBRE_CONFIG).exists()


def test_comprueba_las_dependencias_de_requirements():
    linea = re.search(r"'-c', 'import ([^']+)'", texto_ps1()).group(1)
    for modulo in linea.split(", "):
        __import__(modulo)
