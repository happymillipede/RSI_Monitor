"""Alerta: no se repite mientras el pop-up está abierto y se rearma después de cerrarlo."""

import threading

import pytest

from calibracion import comprobar_reposo
from configuracion import FATIGUE_ALERT_THRESHOLD
from fatiga import AnalizadorFatiga
from grabacion import archivos_siguientes, grabar
from procesamiento import BITalinoSimulado
from tests.cuaderno import VELOCIDAD_SIN_ESPERA

DURACION_S = 300
REARME_S = 30


def grabar_fatiga(tmp_path, rearme_s, cerrar_popup):
    dispositivo = BITalinoSimulado(velocidad=VELOCIDAD_SIN_ESPERA, modo="fatiga", duracion=120)
    analizador = AnalizadorFatiga(comprobar_reposo(dispositivo), FATIGUE_ALERT_THRESHOLD, rearme_alerta_s=rearme_s)
    alertas = []

    def publicar(estado, resultado, mediciones, final):
        resumen = resultado.resumen if resultado else final
        if resumen is not None and resumen.alerta:
            alertas.append(resumen.tiempo)
            if cerrar_popup:
                analizador.cerrar_alerta()

    grabar(dispositivo, analizador, archivos_siguientes(tmp_path), threading.Event(), publicar, DURACION_S)
    return alertas


def test_sin_cerrar_el_popup_no_hay_alertas_repetidas(tmp_path):
    assert len(grabar_fatiga(tmp_path, REARME_S, cerrar_popup=False)) == 1


def test_al_cerrar_el_popup_se_rearma_despues_de_la_pausa(tmp_path):
    alertas = grabar_fatiga(tmp_path, REARME_S, cerrar_popup=True)
    assert len(alertas) >= 2
    for anterior, siguiente in zip(alertas, alertas[1:]):
        assert siguiente - anterior >= REARME_S


def test_sin_rearme_es_como_el_notebook(tmp_path):
    assert len(grabar_fatiga(tmp_path, None, cerrar_popup=True)) == 1


def test_umbral_fuera_de_rango():
    with pytest.raises(ValueError):
        AnalizadorFatiga(None, 120)
