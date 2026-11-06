"""
La regla replicada (nucleo/regla_fatiga.py) debe dar los mismos resultados que la
función cerrar_intervalo() del original.

La prueba extrae con ast la función REAL del original y la ejecuta con gráficos
falsos (no hace falta matplotlib). Las dos reciben los mismos bloques sintéticos.
"""

import ast
import math
import statistics

import numpy as np
import pytest

from nucleo.cargador_original import leer_sin_magicos
from nucleo.regla_fatiga import ReglaFatiga


class Nada:
    """Reemplaza los objetos de matplotlib: acepta cualquier llamada y no hace nada."""

    def __getattr__(self, nombre):
        return lambda *args, **kwargs: None


class EscritorEnMemoria:
    def __init__(self):
        self.filas = []

    def writerow(self, fila):
        self.filas.append(list(fila))


def funcion_del_original(original, nombre, globales):
    arbol = ast.parse(leer_sin_magicos(original.ruta))
    nodo = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == nombre)
    exec(compile(ast.Module(body=[nodo], type_ignores=[]), str(original.ruta), "exec"), globales)
    return globales[nombre]


def globales_del_original(constantes, parametros):
    """Variables globales que usa cerrar_intervalo() (líneas 169-233 del original)."""
    return {
        "math": math,
        "statistics": statistics,
        "print": lambda *args, **kwargs: None,
        "TREND_WINDOW_S": constantes["TREND_WINDOW_S"],
        "RMS_INCREASE_THRESHOLD": parametros["RMS_INCREASE_THRESHOLD"],
        "MDF_DECREASE_THRESHOLD": parametros["MDF_DECREASE_THRESHOLD"],
        "baseline_points_needed": math.ceil(parametros["BASELINE_DURATION_S"] / parametros["TREND_INTERVAL_S"]),
        "persistence_points_needed": math.ceil(parametros["ALERT_PERSISTENCE_S"] / parametros["TREND_INTERVAL_S"]),
        "baseline_rms": [],
        "baseline_mdf": [],
        "fatigue_pattern_streak": 0,
        "fatigue_alerted": False,
        "tiempos_tendencia": [],
        "rms_tendencia": [],
        "mdf_tendencia": [],
        "bin_tiempos": [],
        "bin_rms": [],
        "bin_mdf": [],
        "linea_rms": Nada(),
        "linea_mdf": Nada(),
        "ax_rms": Nada(),
        "ax_mdf": Nada(),
        "grafico": Nada(),
        "fig": Nada(),
    }


def bloques_sinteticos(semilla, cantidad=120):
    """Bloques de 1 s: línea base estable, tramos con patrón de fatiga, cortes y valores NaN."""
    rng = np.random.default_rng(semilla)
    bloques = []
    for k in range(cantidad):
        tiempo = k + 0.5005  # tiempo medio de un bloque de 1000 muestras
        fatiga = 20 <= k < 30 or 45 <= k < 52 or k >= 70
        rms = (13.0 if fatiga else 10.0) + rng.normal(0, 0.4)
        mdf = (78.0 if fatiga else 100.0) + rng.normal(0, 3)
        if rng.random() < 0.05:
            mdf = float("nan")
        if rng.random() < 0.02:
            rms = float("nan")
        bloques.append((tiempo, rms, mdf))
    return bloques


CASOS = [
    # TREND_INTERVAL_S, BASELINE_DURATION_S, ALERT_PERSISTENCE_S, RMS, MDF
    (1, 5, 5, 0.20, 0.15),
    (2, 6, 4, 0.20, 0.15),
    (1, 1, 1, 0.05, 0.01),
    (3, 10, 9, 0.25, 0.20),
    (1, 5, 30, 0.20, 0.15),
]


def iguales(a, b):
    return np.allclose(np.array(a, dtype=float), np.array(b, dtype=float), equal_nan=True, rtol=0, atol=0)


NOMBRES = ("TREND_INTERVAL_S", "BASELINE_DURATION_S", "ALERT_PERSISTENCE_S",
           "RMS_INCREASE_THRESHOLD", "MDF_DECREASE_THRESHOLD")


def comparar_con_original(original, parametros, bloques):
    # --- Original: cerrar_intervalo() real + el agrupamiento de las líneas 427-440 ---
    g = globales_del_original(original.constantes, parametros)
    cerrar_intervalo = funcion_del_original(original, "cerrar_intervalo", g)
    escritor = EscritorEnMemoria()
    estados_original = []

    def cerrar_y_anotar():
        cerrar_intervalo(escritor, Nada())
        estados_original.append((g["fatigue_pattern_streak"], g["fatigue_alerted"], len(g["baseline_rms"])))

    intervalo_actual = None
    for tiempo_bloque, rms, mdf in bloques:
        intervalo = int(tiempo_bloque // parametros["TREND_INTERVAL_S"])
        if intervalo_actual is not None and intervalo != intervalo_actual:
            cerrar_y_anotar()
        intervalo_actual = intervalo
        g["bin_tiempos"].append(tiempo_bloque)
        g["bin_rms"].append(rms)
        g["bin_mdf"].append(mdf)
    cerrar_y_anotar()

    # --- Réplica ---
    regla = ReglaFatiga.desde_parametros(parametros)
    filas = []
    estados_replica = []

    def anotar(resumen):
        filas.append([resumen.tiempo, resumen.rms, resumen.mdf])
        estados_replica.append((regla.racha, regla.alertada, len(regla.linea_base_rms)))

    for tiempo_bloque, rms, mdf in bloques:
        resumen = regla.agregar_bloque(tiempo_bloque, rms, mdf)
        if resumen is not None:
            anotar(resumen)
    anotar(regla.cerrar_intervalo())

    assert iguales(filas, escritor.filas)
    assert estados_replica == estados_original
    assert iguales(regla.linea_base_rms, g["baseline_rms"])
    assert iguales(regla.linea_base_mdf, g["baseline_mdf"])
    return g["fatigue_alerted"]


@pytest.mark.parametrize("caso", CASOS)
@pytest.mark.parametrize("semilla", [1, 2, 3])
def test_regla_igual_al_original(original, caso, semilla):
    comparar_con_original(original, dict(zip(NOMBRES, caso)), bloques_sinteticos(semilla))


@pytest.mark.parametrize("caso", CASOS)
def test_regla_igual_al_original_justo_en_el_umbral(original, caso):
    """Valores exactamente en el umbral: revisa que se use >= y <= como en el original."""
    parametros = dict(zip(NOMBRES, caso))
    rms_borde = 10.0 * (1 + parametros["RMS_INCREASE_THRESHOLD"])
    mdf_borde = 100.0 * (1 - parametros["MDF_DECREASE_THRESHOLD"])
    bloques = [(k + 0.5005, 10.0, 100.0) for k in range(12)]
    bloques += [(k + 0.5005, rms_borde, mdf_borde) for k in range(12, 60)]

    assert comparar_con_original(original, parametros, bloques)


def test_alerta_una_sola_vez_hasta_rearmar():
    regla = ReglaFatiga(intervalo_s=1, linea_base_s=2, persistencia_s=2, umbral_rms=0.2, umbral_mdf=0.15)
    alertas = []
    for k in range(20):
        fatiga = k >= 2
        resumen = regla.agregar_bloque(k + 0.5, 13.0 if fatiga else 10.0, 80.0 if fatiga else 100.0)
        if resumen and resumen.alerta:
            alertas.append(k)
            if len(alertas) == 1:
                base_antes = regla.linea_base()
        if k == 10:
            regla.rearmar()

    # Primera alerta tras 2 intervalos con patrón; la segunda solo después de rearmar.
    assert len(alertas) == 2
    assert alertas[1] > 10
    assert regla.linea_base() == base_antes


def test_pausada_no_evalua_ni_toma_linea_base():
    regla = ReglaFatiga(intervalo_s=1, linea_base_s=2, persistencia_s=1, umbral_rms=0.2, umbral_mdf=0.15)
    regla.pausada = True
    for k in range(5):
        regla.agregar_bloque(k + 0.5, 10.0, 100.0)
    assert regla.calibrando()

    regla.pausada = False
    for k in range(5, 8):
        regla.agregar_bloque(k + 0.5, 10.0, 100.0)
    assert not regla.calibrando()

    regla.pausada = True
    for k in range(8, 15):
        resumen = regla.agregar_bloque(k + 0.5, 13.0, 80.0)
        assert not (resumen and resumen.alerta)
    assert regla.racha == 0
