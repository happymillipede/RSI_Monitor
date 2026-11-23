"""
La app da exactamente los mismos resultados que el notebook 4.2 del grupo.

Se corre el código del notebook (tests/cuaderno.py) y el de la app con la misma señal
simulada, y se comparan byte a byte los tres CSV, la calibración de reposo, la MVC y
las alertas.
"""

import filecmp
import threading

import pytest

from calibracion import calibrar_mvc, comprobar_reposo
from configuracion import FATIGUE_ALERT_THRESHOLD
from fatiga import AnalizadorFatiga
from grabacion import archivos_siguientes, grabar
from procesamiento import BITalinoSimulado
from tests.cuaderno import VELOCIDAD_SIN_ESPERA, ejecutar_notebook

DURACION_PRUEBA_S = 120  # 2 min de señal simulada (corre en ~1 s)
ARCHIVOS = ("EMG_Test01.csv", "EMG_Test01_bloques.csv", "EMG_Test01_crudo.csv")


def grabar_con_la_app(carpeta, modo, duracion_s, con_mvc=False):
    """Lo mismo que hace la ventana: Calibrar, (MVC), Comenzar y grabar hasta el final."""
    dispositivo = BITalinoSimulado(velocidad=VELOCIDAD_SIN_ESPERA, modo=modo, duracion=duracion_s)
    reposo = comprobar_reposo(dispositivo)
    mvc = calibrar_mvc(dispositivo, reposo, dormir=lambda segundos: None) if con_mvc else None
    analizador = AnalizadorFatiga(reposo, FATIGUE_ALERT_THRESHOLD, mvc_rms=mvc)
    alertas = []

    def publicar(estado, resultado, mediciones, final):
        for resumen in (resultado.resumen if resultado else None, final):
            if resumen is not None and resumen.alerta:
                alertas.append(resumen.mensajes[0])

    grabar(dispositivo, analizador, archivos_siguientes(carpeta), threading.Event(), publicar, duracion_s)
    return reposo, mvc, alertas


def comparar(tmp_path, modo, duracion_s, con_mvc=False):
    carpeta_notebook = tmp_path / "notebook"
    carpeta_app = tmp_path / "app"
    carpeta_notebook.mkdir()
    carpeta_app.mkdir()
    espacio, impreso, alertas_notebook = ejecutar_notebook(carpeta_notebook, modo, duracion_s, con_mvc)
    reposo, mvc, alertas_app = grabar_con_la_app(carpeta_app, modo, duracion_s, con_mvc)

    for nombre in ARCHIVOS:
        assert filecmp.cmp(carpeta_notebook / nombre, carpeta_app / nombre, shallow=False), nombre
    assert reposo.paso == espacio["rest_check_passed"]
    assert reposo.rms_mediana == espacio["rest_rms_median"]
    assert reposo.rms_sd_robusta == espacio["rest_rms_robust_sd"]
    for linea in reposo.lineas:
        assert linea in impreso, linea
    assert mvc == espacio["MVC_RMS"]
    assert len(alertas_app) == len(alertas_notebook)
    for alerta_app, alerta_notebook in zip(alertas_app, alertas_notebook):
        assert alerta_app in alerta_notebook
    return alertas_app


def test_fatiga_igual_al_notebook_y_alerta(tmp_path):
    alertas = comparar(tmp_path, "fatiga", DURACION_PRUEBA_S)
    assert len(alertas) == 1


@pytest.mark.parametrize("modo", ["normal", "contraccion"])
def test_sin_fatiga_igual_al_notebook_y_sin_alerta(tmp_path, modo):
    assert comparar(tmp_path, modo, DURACION_PRUEBA_S) == []


def test_con_mvc_igual_al_notebook(tmp_path):
    comparar(tmp_path, "fatiga", DURACION_PRUEBA_S, con_mvc=True)
    encabezado = (tmp_path / "app" / "EMG_Test01.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "RMS (%MVC)" in encabezado


def test_diez_minutos_como_el_notebook(tmp_path):
    """La DURACION del notebook (10 min): la alerta sale a los ~317 s, igual en los dos."""
    alertas = comparar(tmp_path, "fatiga", 10 * 60)
    assert len(alertas) == 1
