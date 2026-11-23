"""Conexión con el BITalino, con puertos y dispositivos imitados (sin hardware)."""

import threading
import time
from types import SimpleNamespace

import pytest

from conexion import (
    BitalinoConLimite,
    conectar_automatico,
    ejecutar_con_limite,
    explicar_error,
    lista_candidatos,
    puertos_detectados,
    todos_los_puertos,
)

LIMITE_CORTO_S = 0.2


def test_windows_solo_bluetooth_y_el_entrante_al_final():
    puertos = [
        SimpleNamespace(device="COM1", hwid="ACPI\\PNP0501\\1"),
        SimpleNamespace(device="COM4", hwid="BTHENUM\\{00001101}_LOCALMFG&0000"),
        SimpleNamespace(device="COM5", hwid="BTHENUM\\{00001101}_LOCALMFG&000F"),
    ]
    assert puertos_detectados("win32", listar=lambda: puertos) == ["COM5", "COM4"]


def test_macos_busca_bitalino_en_el_nombre():
    archivos = ["/dev/tty.Bluetooth-Incoming-Port", "/dev/tty.BITalino-DevB"]
    assert puertos_detectados("darwin", listar=list, buscar_archivos=lambda patron: archivos) == ["/dev/tty.BITalino-DevB"]


def test_todos_los_puertos_detectados_primero():
    otros = [SimpleNamespace(device="COM1"), SimpleNamespace(device="COM5")]
    assert todos_los_puertos(["COM5"], listar=lambda: otros) == ["COM5", "COM1"]


def test_orden_de_los_candidatos():
    assert lista_candidatos("COM5", "/dev/tty.bitalino", ["COM3", "COM5"]) == ["COM5", "/dev/tty.bitalino", "COM3"]


def test_ejecutar_con_limite_no_se_cuelga():
    inicio = time.monotonic()
    with pytest.raises(TimeoutError):
        ejecutar_con_limite(threading.Event().wait, LIMITE_CORTO_S)
    assert time.monotonic() - inicio < 1


class PuertoFalso:
    def __init__(self):
        self.cerrado = threading.Event()

    def close(self):
        self.cerrado.set()


class BitalinoFalso:
    """Imita bitalino.BITalino. 'mudo' = no responde nunca a la versión."""

    mudo = False

    def __init__(self, puerto):
        self.socket = PuertoFalso()
        self.version()

    def version(self):
        if self.mudo:
            self.socket.cerrado.wait()
            raise OSError("puerto cerrado")
        return "BITalino_v5.1"

    def start(self, fs, canales):
        pass

    def read(self, n):
        return [[0, 0, 0, 0, 0, 512]] * n

    def stop(self):
        pass


def test_bitalino_con_limite_funciona_como_el_original():
    dispositivo = BitalinoConLimite("COM5", LIMITE_CORTO_S, clase_bitalino=BitalinoFalso)
    assert dispositivo.version() == "BITalino_v5.1"
    dispositivo.start(1000, [0])
    assert len(dispositivo.read(10)) == 10
    dispositivo.stop()
    dispositivo.close()


def test_si_no_responde_se_cierra_el_puerto():
    class Mudo(BitalinoFalso):
        mudo = True

    with pytest.raises(TimeoutError):
        BitalinoConLimite("COM5", LIMITE_CORTO_S, clase_bitalino=Mudo)


def test_conectar_automatico_prueba_cada_puerto():
    probados = []

    def abrir(puerto, limite_s, detener):
        probados.append(puerto)
        if puerto != "COM7":
            raise OSError(f"could not open port '{puerto}'")
        return puerto

    assert conectar_automatico(["COM3", "COM7"], 1, abrir=abrir) == "COM7"
    assert probados == ["COM3", "COM7"]
    with pytest.raises(LookupError, match="COM3: no se pudo abrir el puerto"):
        conectar_automatico(["COM3"], 1, abrir=abrir)
    with pytest.raises(LookupError, match="emparejado"):
        conectar_automatico([], 1, abrir=abrir)


def test_errores_en_palabras_simples():
    assert "no respondió" in explicar_error("COM3", TimeoutError("x"))
    assert "ocupado" in explicar_error("COM3", PermissionError("x"))
