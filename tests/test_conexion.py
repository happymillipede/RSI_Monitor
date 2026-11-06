"""Conexión con el BITalino real, probada con puertos y dispositivos imitados."""

import threading
import time
from types import SimpleNamespace

import pytest

from nucleo.adquisicion import BUSCANDO, CALIBRANDO, CONECTANDO, MIDIENDO, Oyente, SesionMedicion
from nucleo.conexion import (
    BitalinoConLimite,
    ConectorBitalino,
    ejecutar_con_limite,
    lista_candidatos,
    puertos_detectados,
    tiempo_de_espera,
)
from nucleo.simulador import DispositivoSimulado
from tests.utilidades import parametros_del_original

LIMITE_CORTO_S = 0.2


# --- Lista de puertos ---


def test_orden_de_los_candidatos_sin_repetir():
    assert lista_candidatos(None, "COM5", "/dev/tty.bitalino", ["COM3", "COM5", "COM4"]) == [
        "COM5",
        "/dev/tty.bitalino",
        "COM3",
        "COM4",
    ]
    assert lista_candidatos(None, None, "/dev/tty.bitalino", []) == ["/dev/tty.bitalino"]


def test_el_puerto_manual_reemplaza_a_todos():
    assert lista_candidatos("COM9", "COM5", "/dev/tty.bitalino", ["COM3"]) == ["COM9"]


def test_windows_solo_puertos_bluetooth_y_el_entrante_al_final():
    puertos = [
        SimpleNamespace(device="COM1", hwid="ACPI\\PNP0501\\1"),
        SimpleNamespace(device="COM4", hwid="BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000"),
        SimpleNamespace(device="COM3", hwid="USB VID:PID=2341:0043"),
        SimpleNamespace(device="COM5", hwid="BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&000F"),
    ]
    assert puertos_detectados("win32", listar=lambda: puertos) == ["COM5", "COM4"]


def test_macos_busca_tty_con_bitalino_en_el_nombre():
    archivos = ["/dev/tty.Bluetooth-Incoming-Port", "/dev/tty.BITalino-DevB", "/dev/tty.usbserial"]
    assert puertos_detectados("darwin", listar=list, buscar_archivos=lambda patron: archivos) == [
        "/dev/tty.BITalino-DevB"
    ]


def test_linux_usa_rfcomm():
    assert puertos_detectados("linux", listar=list, buscar_archivos=lambda patron: ["/dev/rfcomm0"]) == [
        "/dev/rfcomm0"
    ]


def test_espera_creciente_con_maximo():
    assert [tiempo_de_espera(i, 1, 30) for i in range(7)] == [1, 2, 4, 8, 16, 30, 30]


# --- Límite de tiempo ---


def test_ejecutar_con_limite_devuelve_o_relanza():
    assert ejecutar_con_limite(lambda: 42, 1) == 42
    with pytest.raises(ValueError):
        ejecutar_con_limite(lambda: int("x"), 1)


def test_ejecutar_con_limite_no_se_cuelga():
    nunca = threading.Event()
    inicio = time.monotonic()
    with pytest.raises(TimeoutError):
        ejecutar_con_limite(nunca.wait, LIMITE_CORTO_S)
    assert time.monotonic() - inicio < 1


class PuertoFalso:
    """Imita serial.Serial: close() desbloquea una lectura que estaba esperando."""

    def __init__(self):
        self.cerrado = threading.Event()

    def close(self):
        self.cerrado.set()


class BitalinoFalso:
    """Imita bitalino.BITalino. 'mudo' = no responde nunca a la versión."""

    mudo = False
    lectura_colgada = False

    def __init__(self, puerto):
        self.socket = PuertoFalso()
        self.version()

    def version(self):
        if self.mudo:
            self.socket.cerrado.wait()
            raise OSError("puerto cerrado")
        return "BITalino_v5.1"

    def start(self, fs, canales):
        self.canales = canales

    def read(self, n):
        if self.lectura_colgada:
            self.socket.cerrado.wait()
            raise OSError("puerto cerrado")
        return [[0, 0, 0, 0, 0, 512]] * n

    def stop(self):
        pass


def test_bitalino_con_limite_funciona_como_el_original():
    dispositivo = BitalinoConLimite("COM5", LIMITE_CORTO_S, BitalinoFalso)
    assert dispositivo.version() == "BITalino_v5.1"
    dispositivo.start(1000, [0])
    assert len(dispositivo.read(10)) == 10
    dispositivo.stop()
    dispositivo.close()
    assert dispositivo.dispositivo.socket.cerrado.is_set()


def test_si_no_responde_la_version_se_cierra_el_puerto():
    class Mudo(BitalinoFalso):
        mudo = True

    with pytest.raises(TimeoutError):
        BitalinoConLimite("COM5", LIMITE_CORTO_S, Mudo)


def test_si_la_lectura_se_cuelga_se_corta_y_se_cierra_el_puerto():
    dispositivo = BitalinoConLimite("COM5", LIMITE_CORTO_S, BitalinoFalso)
    dispositivo.start(1000, [0])
    dispositivo.dispositivo.lectura_colgada = True
    with pytest.raises(TimeoutError):
        dispositivo.read(10)
    assert dispositivo.dispositivo.socket.cerrado.is_set()


# --- Búsqueda con reintentos ---


class DetenerFalso:
    """Imita threading.Event, pero wait() no espera: anota cuánto habría esperado."""

    def __init__(self, detener_despues_de=None):
        self.esperas = []
        self.detener_despues_de = detener_despues_de

    def is_set(self):
        return self.detener_despues_de is not None and len(self.esperas) >= self.detener_despues_de

    def wait(self, segundos):
        self.esperas.append(segundos)
        return self.is_set()


def conexion_por_defecto(**cambios):
    conexion = {
        "puerto_manual": None,
        "ultimo_puerto": "COM5",
        "timeout_s": 5,
        "espera_inicial_s": 1,
        "espera_maxima_s": 30,
    }
    conexion.update(cambios)
    return conexion


def test_prueba_cada_puerto_y_reintenta_con_espera_creciente():
    probados = []

    def abrir(puerto, limite_s):
        probados.append(puerto)
        if len(probados) < 7:
            raise TimeoutError("no responde")
        return f"BITalino en {puerto}"

    avisos = []
    conector = ConectorBitalino(conexion_por_defecto(), "/dev/tty.bitalino", abrir, lambda: ["COM3"])
    detener = DetenerFalso()
    dispositivo = conector(detener, lambda estado, detalle: avisos.append(estado))

    assert dispositivo == "BITalino en COM5"
    assert probados == ["COM5", "/dev/tty.bitalino", "COM3"] * 2 + ["COM5"]
    assert detener.esperas == [1, 2]
    assert BUSCANDO in avisos and CONECTANDO in avisos


def test_apagar_mientras_busca_devuelve_none():
    def abrir(puerto, limite_s):
        raise OSError("no existe")

    conector = ConectorBitalino(conexion_por_defecto(), "/dev/tty.bitalino", abrir, list)
    assert conector(DetenerFalso(detener_despues_de=3), lambda *aviso: None) is None


def test_con_puerto_manual_solo_prueba_ese():
    probados = []

    def abrir(puerto, limite_s):
        probados.append(puerto)
        return puerto

    conector = ConectorBitalino(conexion_por_defecto(puerto_manual="COM9"), "/dev/tty.bitalino", abrir, lambda: ["COM3"])
    assert conector(DetenerFalso(), lambda *aviso: None) == "COM9"
    assert probados == ["COM9"]


# --- Reconexión durante la medición ---


class SimuladoQueSeCorta(DispositivoSimulado):
    """BITalino simulado con puerto, cuya lectura falla una vez después de 'bloques_hasta_corte'."""

    def __init__(self, puerto, bloques_hasta_corte, *argumentos):
        super().__init__(*argumentos)
        self.puerto = puerto
        self.bloques_hasta_corte = bloques_hasta_corte
        self.lecturas = 0
        self.cerrado = False

    def read(self, n):
        self.lecturas += 1
        if self.lecturas == self.bloques_hasta_corte:
            raise OSError("se perdió el Bluetooth")
        return super().read(n)

    def close(self):
        self.cerrado = True


class OyenteReconexion(Oyente):
    def __init__(self):
        self.estados = []
        self.puertos = []
        self.resumenes = []
        self.sesion = None

    def al_cambiar_estado(self, estado, detalle=""):
        self.estados.append(estado)

    def al_conectar(self, puerto):
        self.puertos.append(puerto)

    def al_cerrar_intervalo(self, resumen, linea_base):
        self.resumenes.append(resumen)
        if len(self.resumenes) >= 20:
            self.sesion.detener()


def test_la_sesion_se_reconecta_sin_perder_la_linea_base(original, tmp_path):
    constantes = original.constantes
    dispositivos = []

    def abrir_dispositivo(detener, avisar):
        avisar(BUSCANDO, "Buscando el BITalino…")
        puerto = f"COM{len(dispositivos) + 5}"
        # El primero se corta en la lectura 12; el segundo no se corta.
        corte = 12 if not dispositivos else 0
        dispositivo = SimuladoQueSeCorta(puerto, corte, "normal", original.fs, constantes["SIM_BASELINE_DURATION_S"], None)
        dispositivos.append(dispositivo)
        return dispositivo

    oyente = OyenteReconexion()
    sesion = SesionMedicion(
        original, parametros_del_original(constantes), abrir_dispositivo, tmp_path, "prueba", oyente, reconectar=True
    )
    oyente.sesion = sesion
    procesador_inicial = sesion.procesador_emg
    sesion.ejecutar()

    assert oyente.puertos == ["COM5", "COM6"]
    assert dispositivos[0].cerrado
    assert sesion.procesador_emg is not procesador_inicial  # filtro nuevo tras reconectar
    # Calibra, mide, se corta, reconecta y sigue midiendo (la línea base ya estaba lista)
    assert oyente.estados.index(CALIBRANDO) < oyente.estados.index(MIDIENDO)
    despues_del_corte = oyente.estados[oyente.estados.index(MIDIENDO) + 1 :]
    assert despues_del_corte[:2] == [CONECTANDO, BUSCANDO]
    assert MIDIENDO in despues_del_corte
    assert len(sesion.regla.linea_base_rms) == sesion.regla.puntos_linea_base
    assert len(oyente.resumenes) >= 20
    filas = sesion.ruta_csv.read_text(encoding="utf-8").strip().splitlines()
    assert len(filas) == len(oyente.resumenes) + 1  # un solo CSV para toda la sesión
