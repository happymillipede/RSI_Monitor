"""
La simulación de la app (DispositivoSimulado + SesionMedicion + ReglaFatiga) debe
producir el mismo CSV y la misma alerta que la celda de simulación del original.

La prueba ejecuta la celda REAL del original ("Synthetic EMG trend test") con
matplotlib e IPython falsos y una duración más corta (cambiada con ast).
"""

import ast
import csv
import sys
import types

import numpy as np
import pytest

from nucleo.cargador_original import leer_sin_magicos
from tests.utilidades import simular

DURACION_PRUEBA_S = 40


class Nada:
    def __getattr__(self, nombre):
        return lambda *args, **kwargs: None


class EjeFalso(Nada):
    def plot(self, *args, **kwargs):
        return [Nada()]


def modulos_falsos(monkeypatch):
    """Reemplaza matplotlib.pyplot e IPython.display por versiones que no dibujan."""
    pyplot = types.ModuleType("matplotlib.pyplot")
    pyplot.subplots = lambda *args, **kwargs: (Nada(), (EjeFalso(), EjeFalso()))
    pyplot.show = lambda *args, **kwargs: None
    matplotlib = types.ModuleType("matplotlib")
    matplotlib.pyplot = pyplot

    display = types.ModuleType("IPython.display")
    display.display = lambda *args, **kwargs: Nada()
    ipython = types.ModuleType("IPython")
    ipython.display = display

    for nombre, modulo in [("matplotlib", matplotlib), ("matplotlib.pyplot", pyplot),
                           ("IPython", ipython), ("IPython.display", display)]:
        monkeypatch.setitem(sys.modules, nombre, modulo)


def celda_simulacion(original, escenario, ruta_csv):
    """Última celda del original, con duración, escenario y archivo de salida cambiados."""
    celda = leer_sin_magicos(original.ruta).split("# %%")[-1]
    arbol = ast.parse(celda)
    reemplazos = {
        "SIM_DURATION_S": DURACION_PRUEBA_S,
        "SIM_SCENARIO": escenario,
        "SIM_OUTPUT_CSV": str(ruta_csv),
    }
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and isinstance(nodo.targets[0], ast.Name):
            if nodo.targets[0].id in reemplazos:
                nuevo = ast.Constant(reemplazos[nodo.targets[0].id])
                nodo.value = ast.copy_location(nuevo, nodo.value)
    return compile(arbol, "celda_simulacion", "exec")


def leer_csv(ruta):
    with open(ruta, newline="", encoding="utf-8") as archivo:
        filas = list(csv.reader(archivo))
    return filas[0], np.array(filas[1:], dtype=float)


@pytest.mark.parametrize("escenario", ["normal", "fatigue_test"])
def test_simulacion_igual_al_original(original, escenario, tmp_path, monkeypatch, capsys):
    modulos_falsos(monkeypatch)
    ruta_original = tmp_path / "original.csv"
    globales = {
        "PERIODO": original.constantes["PERIODO"],
        "N": original.constantes["N"],
        "ProcesadorEMG": original.ProcesadorEMG,
    }
    exec(celda_simulacion(original, escenario, ruta_original), globales)
    capsys.readouterr()

    sesion, oyente = simular(original, tmp_path, escenario, DURACION_PRUEBA_S, sim=True)

    encabezado_original, datos_original = leer_csv(ruta_original)
    encabezado_app, datos_app = leer_csv(sesion.ruta_csv)

    assert encabezado_app == encabezado_original
    assert datos_app.shape == datos_original.shape
    # El tiempo se calcula como n*PERIODO (app) o n/FS (original): difiere solo en redondeo.
    assert np.allclose(datos_app[:, 0], datos_original[:, 0], rtol=0, atol=1e-9)
    assert np.allclose(datos_app[:, 1:], datos_original[:, 1:], rtol=1e-12, atol=0, equal_nan=True)
    assert bool(oyente.alertas) == globales["fatigue_alerted"]
