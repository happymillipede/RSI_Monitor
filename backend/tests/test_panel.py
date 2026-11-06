"""Texto del panel de información (réplica de actualizar_panel_adquisicion) y textos de estado."""

import numpy as np

from app.nucleo.adquisicion import InfoBloque
from tests.utilidades import parametros_del_original
from app.textos import texto_calibracion, texto_linea_base, texto_panel


def test_panel_tiene_los_mismos_datos_que_el_original(original):
    trama = np.array([7, 0, 0, 0, 0, 506])
    info = InfoBloque(
        n_medicion=57000,
        ultimo_valor_emg=506,
        ultimo_rms=15.94211,
        ultimo_mdf=106.0123,
        ultima_trama=trama,
        muestras_recientes=[(56.999, 495), (57.0, 506)],
    )
    parametros = parametros_del_original(original.constantes)
    texto = texto_panel(info, original.constantes, parametros, "Midiendo")

    for linea in [
        "BITALINO — ADQUISICIÓN Y PROCESAMIENTO",
        "Estado: Midiendo",
        "Canal configurado: 0",
        "PERIODO: 0.001 s",
        "FS (1 / PERIODO): 1000.00 Hz",
        "Tamaño máximo de lectura N: 1000",
        "Umbral RMS: +20%",
        "Umbral MDF: -15%",
        "Muestras recibidas: 57000",
        "Último valor EMG (ADC): 506",
        "Último RMS del bloque: 15.942",
        "Última MDF del bloque: 106.012 Hz",
        repr(trama),
        "Últimas 2 muestras:",
        "  t=  57.000 s | EMG=506",
        "device.stop() -> detiene adquisición",
    ]:
        assert linea in texto, linea


def test_panel_recorta_trama_larga(original):
    info = InfoBloque(0, float("nan"), float("nan"), float("nan"), "x" * 500, [])
    texto = texto_panel(info, original.constantes, parametros_del_original(original.constantes), "Midiendo")
    assert repr("x" * 500)[:157] + "...\n" in texto
    assert "Todavía no hay muestras." in texto


def test_textos_de_calibracion_y_linea_base():
    assert texto_calibracion(5) == (
        "Calibrando línea base (5 s): mantén tu postura y ritmo de trabajo normales."
    )
    assert texto_linea_base(16.0721, 190.8139) == "Línea base: RMS = 16.072 ADC · MDF = 190.814 Hz"
