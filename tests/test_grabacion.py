"""Grabación: numeración de los CSV, Detener y límite de duración."""

import csv
import threading

import pytest

from calibracion import comprobar_reposo
from configuracion import FATIGUE_ALERT_THRESHOLD, PERIODO
from fatiga import AnalizadorFatiga
from grabacion import archivos_siguientes, grabar
from procesamiento import BITalinoSimulado
from tests.cuaderno import VELOCIDAD_SIN_ESPERA


def test_numeracion_como_el_notebook(tmp_path):
    assert archivos_siguientes(tmp_path).tendencias.name == "EMG_Test01.csv"
    (tmp_path / "EMG_Test07_crudo.csv").write_text("")
    (tmp_path / "EMG_Test03(1).csv").write_text("")
    archivos = archivos_siguientes(tmp_path)
    assert [ruta.name for ruta in (archivos.tendencias, archivos.crudo, archivos.bloques)] == [
        "EMG_Test08.csv", "EMG_Test08_crudo.csv", "EMG_Test08_bloques.csv"
    ]


def test_sobrescribir_usa_siempre_test01(tmp_path):
    (tmp_path / "EMG_Test05.csv").write_text("")
    assert archivos_siguientes(tmp_path, sobrescribir=True).tendencias.name == "EMG_Test01.csv"


def test_detener_corta_la_grabacion_y_guarda_el_intervalo_parcial(tmp_path):
    dispositivo = BITalinoSimulado(velocidad=VELOCIDAD_SIN_ESPERA, modo="normal")
    analizador = AnalizadorFatiga(comprobar_reposo(dispositivo), FATIGUE_ALERT_THRESHOLD)
    detener = threading.Event()
    segundos = []

    def publicar(estado, resultado, mediciones, final):
        segundos.append(estado.n_medicion * PERIODO)
        if estado.n_medicion * PERIODO >= 12.5:
            detener.set()

    archivos = archivos_siguientes(tmp_path)
    estado = grabar(dispositivo, analizador, archivos, detener, publicar)
    assert estado.n_medicion == 13000  # se detiene al terminar el bloque en curso
    assert dispositivo.iniciado is False  # se llamó a stop()
    with open(archivos.tendencias, encoding="utf-8") as archivo:
        filas = list(csv.reader(archivo))
    assert [fila[5] for fila in filas[1:]] == ["False", "False", "True"]  # el último es parcial
    with open(archivos.crudo, encoding="utf-8") as archivo:
        assert sum(1 for _ in archivo) == 13000 + 1


def test_se_corta_sola_al_llegar_al_maximo(tmp_path):
    dispositivo = BITalinoSimulado(velocidad=VELOCIDAD_SIN_ESPERA, modo="normal")
    analizador = AnalizadorFatiga(None, FATIGUE_ALERT_THRESHOLD)
    estado = grabar(dispositivo, analizador, archivos_siguientes(tmp_path), threading.Event(), duracion_maxima_s=7)
    assert estado.n_medicion == 7000


def test_error_de_lectura_igual_detiene_el_dispositivo(tmp_path):
    class Falla(BITalinoSimulado):
        def read(self, cantidad):
            raise OSError("The computer lost communication with the device.")

    dispositivo = Falla(velocidad=VELOCIDAD_SIN_ESPERA)
    with pytest.raises(OSError):
        grabar(dispositivo, AnalizadorFatiga(None, 60), archivos_siguientes(tmp_path), threading.Event())
    assert dispositivo.iniciado is False
