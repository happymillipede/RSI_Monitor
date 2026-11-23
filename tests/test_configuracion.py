"""configuracion.py tiene los mismos valores que el notebook 4.2 (celdas 2, 3 y 7)."""

import pytest

import configuracion
from tests.cuaderno import CELDA_CONFIGURACION, CELDA_ESTADO, CELDA_SIMULADOR, constantes_de_celda

# En la app, DURACION solo la usa el simulador: la grabación sigue hasta Detener.
NOMBRES_SIMULADOR = ("VELOCIDAD_SIMULACION", "MODO_EMG")
NOMBRES_GRAFICOS = ("TREND_WINDOW_S", "RAW_WINDOW_S", "BLOCK_WINDOW_S")
NO_USADOS_EN_LA_APP = {"MVC_RMS", "OFFLINE_CSV_PATH", "OFFLINE_SEGMENT_S", "OFFLINE_SEGMENT_LABELS", "OFFLINE_BLOCK_S"}


@pytest.mark.parametrize("nombre, valor", sorted(constantes_de_celda(CELDA_CONFIGURACION).items()))
def test_celda_2_configuracion(nombre, valor):
    if nombre in NO_USADOS_EN_LA_APP:
        return
    assert getattr(configuracion, nombre) == valor, f"{nombre} no coincide con el notebook"


def test_celda_3_simulador_y_celda_7_graficos():
    simulador = constantes_de_celda(CELDA_SIMULADOR)
    for nombre in NOMBRES_SIMULADOR:
        assert getattr(configuracion, nombre) == simulador[nombre]
    graficos = constantes_de_celda(CELDA_ESTADO)
    for nombre in NOMBRES_GRAFICOS:
        assert getattr(configuracion, nombre) == graficos[nombre]


def test_ajustes_se_guardan_y_lo_que_falta_usa_el_valor_por_defecto(tmp_path):
    assert configuracion.leer_ajustes(tmp_path) == configuracion.AJUSTES_POR_DEFECTO
    ajustes = configuracion.leer_ajustes(tmp_path)
    ajustes["umbral_alerta"] = 50
    configuracion.guardar_ajustes(ajustes, tmp_path)
    leidos = configuracion.leer_ajustes(tmp_path)
    assert leidos["umbral_alerta"] == 50
    assert leidos["rearme_alerta_min"] == configuracion.REARME_ALERTA_MIN
    (tmp_path / configuracion.NOMBRE_AJUSTES).write_text("{ dañado", encoding="utf-8")
    assert configuracion.leer_ajustes(tmp_path) == configuracion.AJUSTES_POR_DEFECTO
