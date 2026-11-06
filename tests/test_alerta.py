"""Texto de la ventana de alerta de fatiga."""

from nucleo.regla_fatiga import ACLARACION_MEDICA
from ui.dialogo_alerta import texto_alerta


def test_texto_exacto_de_la_alerta():
    assert texto_alerta(10) == "Riesgo de fatiga muscular, descanse 10 minutos"
    assert texto_alerta(15) == "Riesgo de fatiga muscular, descanse 15 minutos"


def test_aclaracion_dice_que_no_es_diagnostico():
    assert "no es un diagnóstico médico" in ACLARACION_MEDICA
