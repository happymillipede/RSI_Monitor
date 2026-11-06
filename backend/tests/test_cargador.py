"""Pruebas del cargador ast del código original."""

import ast
import re
import subprocess
import sys
import unicodedata

import numpy as np
import pytest

from app import almacenamiento
from app.nucleo.cargador_original import (
    CONSTANTES_REQUERIDAS,
    ErrorOriginal,
    cargar_original,
    leer_sin_magicos,
)


def valor_en_texto(texto, nombre):
    """Lee 'NOMBRE = valor' con una expresión regular, sin el cargador, para comparar."""
    coincidencias = re.findall(rf"^{nombre}\s*=\s*([^#\n]+)", texto, flags=re.MULTILINE)
    return ast.literal_eval(coincidencias[-1].strip())


def test_encuentra_el_original():
    ruta = almacenamiento.buscar_original()
    assert unicodedata.normalize("NFC", ruta.name) == almacenamiento.NOMBRE_ORIGINAL


def test_constantes_iguales_al_texto_del_original(original):
    texto = original.ruta.read_text(encoding="utf-8")
    for nombre in CONSTANTES_REQUERIDAS:
        assert original.constantes[nombre] == valor_en_texto(texto, nombre), nombre
    assert original.fs == 1 / original.constantes["PERIODO"]


def test_ignora_las_lineas_de_jupyter(original):
    texto = leer_sin_magicos(original.ruta)
    assert "%pip" in original.ruta.read_text(encoding="utf-8")
    assert not any(linea.lstrip().startswith("%") for linea in texto.splitlines())


def test_procesador_emg_funciona(original):
    procesador = original.ProcesadorEMG(original.fs)
    tiempos = np.arange(1, 1001) * original.constantes["PERIODO"]
    rng = np.random.default_rng(0)
    valores = 512 + 20 * rng.normal(size=1000)
    rms, mdf = procesador.procesar_bloque(list(zip(tiempos, valores)))
    assert rms > 0
    assert 25 <= mdf <= 400


def test_procesador_emg_mantiene_validacion_del_original(original):
    with pytest.raises(ValueError):
        original.ProcesadorEMG(500)


def test_no_ejecuta_el_resto_del_original():
    """Cargar el original no debe importar bitalino ni IPython, ni conectarse a nada."""
    codigo = (
        "import sys; from app.nucleo.cargador_original import cargar_original; cargar_original(); "
        "print('bitalino' in sys.modules, 'IPython' in sys.modules, 'matplotlib' in sys.modules)"
    )
    salida = subprocess.run(
        [sys.executable, "-c", codigo], cwd=almacenamiento.RAIZ_BACKEND, capture_output=True, text=True, check=True
    )
    assert salida.stdout.split() == ["False", "False", "False"]


def test_toma_los_cambios_del_original(original, tmp_path):
    texto = original.ruta.read_text(encoding="utf-8")
    texto = texto.replace("RMS_INCREASE_THRESHOLD = 0.20", "RMS_INCREASE_THRESHOLD = 0.33")
    copia = tmp_path / almacenamiento.NOMBRE_ORIGINAL
    copia.write_text(texto, encoding="utf-8")

    assert cargar_original(copia).constantes["RMS_INCREASE_THRESHOLD"] == 0.33


def test_la_clase_puede_usar_constantes_del_original(tmp_path):
    copia = tmp_path / "original.py"
    copia.write_text(
        "%pip install algo\n"
        + "\n".join(f"{nombre} = 1" for nombre in CONSTANTES_REQUERIDAS)
        + "\nFACTOR = 3\n"
        "class ProcesadorEMG:\n"
        "    def __init__(self, fs):\n"
        "        self.factor = FACTOR\n",
        encoding="utf-8",
    )
    assert cargar_original(copia).ProcesadorEMG(1000).factor == 3


def test_avisa_si_falta_una_constante(original, tmp_path):
    texto = original.ruta.read_text(encoding="utf-8").replace("TREND_WINDOW_S = 30", "")
    copia = tmp_path / "original.py"
    copia.write_text(texto, encoding="utf-8")

    with pytest.raises(ErrorOriginal, match="TREND_WINDOW_S"):
        cargar_original(copia)


def test_busca_nombre_con_acento_nfd(tmp_path):
    """macOS puede guardar 'Código' como 'Co' + acento combinado (NFD)."""
    nombre_nfd = unicodedata.normalize("NFD", almacenamiento.NOMBRE_ORIGINAL)
    (tmp_path / nombre_nfd).write_text("x", encoding="utf-8")

    encontrado = almacenamiento.buscar_archivo(tmp_path, almacenamiento.NOMBRE_ORIGINAL)
    assert encontrado is not None
