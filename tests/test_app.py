"""La API que usa la ventana (sin abrir ventanas): conectar, calibrar, grabar, alerta."""

import json
import threading
import time

import numpy as np
import pytest

from app import Api
from configuracion import FATIGUE_ALERT_THRESHOLD, leer_ajustes
from tests.cuaderno import VELOCIDAD_SIN_ESPERA

LIMITE_ESPERA_S = 60


class VentanaFalsa:
    """Anota los mensajes que Python envía a la ventana y si se abrió el pop-up."""

    def __init__(self, api):
        self.mensajes = []
        self.popups = 0
        self.api = api
        api._enviar_js = self.ejecutar
        api._crear_popup = self.abrir_popup
        api._cerrar_popup = lambda: None

    def ejecutar(self, codigo):
        inicio = codigo.index("recibir(") + len("recibir(")
        self.mensajes.append(json.loads(codigo[inicio:codigo.rindex(")")]))

    def abrir_popup(self):
        self.popups += 1

    def tipos(self):
        return {mensaje["tipo"] for mensaje in self.mensajes}


def esperar(condicion):
    fin = time.monotonic() + LIMITE_ESPERA_S
    while not condicion():
        assert time.monotonic() < fin, "se acabó el tiempo de espera"
        time.sleep(0.01)


def esperar_tarea(api):
    esperar(lambda: api._tarea is None)


@pytest.fixture
def api(tmp_path):
    api = Api(tmp_path)
    VentanaFalsa(api)
    yield api
    api._cerrar()


def conectar_simulador(api, modo="fatiga"):
    assert api.conectar({"simulacion": True, "modo": modo, "velocidad": VELOCIDAD_SIN_ESPERA})["ok"]
    assert api.obtener_estado()["conexion"]["estado"] == "Conectado"


def test_estado_inicial(api):
    estado = api.obtener_estado()
    assert estado["conexion"]["estado"] == "Desconectado"
    assert estado["calibracion"]["estado"] == "pendiente"
    assert estado["alerta"]["umbral"] == FATIGUE_ALERT_THRESHOLD
    json.dumps(estado, allow_nan=False)  # JSON válido para JavaScript


def test_no_se_puede_calibrar_ni_comenzar_sin_conectar_y_calibrar(api):
    assert not api.calibrar()["ok"]
    assert not api.comenzar()["ok"]
    conectar_simulador(api)
    assert "calibra" in api.comenzar()["mensaje"]


def test_flujo_completo_con_alerta_y_popup(api, tmp_path):
    ventana = api._enviar_js.__self__
    conectar_simulador(api)
    assert api.calibrar()["ok"]
    esperar_tarea(api)
    assert api.obtener_estado()["calibracion"]["estado"] == "PASS"

    assert api.comenzar()["ok"]
    assert not api.comenzar()["ok"]  # solo una tarea a la vez
    esperar(lambda: api._alerta["pendiente"])
    assert ventana.popups == 1
    assert {"bloque", "tendencia", "alerta"} <= ventana.tipos()
    datos = api.datos_alerta()
    assert datos["pendiente"] and datos["indice"] >= FATIGUE_ALERT_THRESHOLD

    api.cerrar_alerta()
    assert api.obtener_estado()["alerta"]["pendiente"] is False
    api.detener()
    esperar_tarea(api)
    estado = api.obtener_estado()
    assert estado["grabacion"]["activa"] is False
    assert len(estado["grabacion"]["archivos"]) == 3
    assert (tmp_path / "EMG_Test01_crudo.csv").exists()
    assert estado["tendencias"]
    assert "BITALINO — ADQUISICIÓN Y PROCESAMIENTO" in estado["panel"]


def test_porcentaje_de_alerta_se_guarda(api, tmp_path):
    assert api.cambiar_umbral("50")["ok"]
    assert leer_ajustes(tmp_path)["umbral_alerta"] == 50
    assert not api.cambiar_umbral(150)["ok"]
    assert not api.cambiar_umbral("hola")["ok"]
    api.restaurar_umbral()
    assert api.obtener_estado()["alerta"]["umbral"] == FATIGUE_ALERT_THRESHOLD


def test_detener_cancela_la_calibracion(tmp_path):
    api = Api(tmp_path)
    VentanaFalsa(api)
    assert api.conectar({"simulacion": True, "modo": "normal", "velocidad": 1})["ok"]  # tiempo real: 15 s
    api.calibrar()
    time.sleep(0.3)
    api.detener()
    esperar_tarea(api)
    assert api.obtener_estado()["calibracion"]["estado"] == "pendiente"
    api._cerrar()


class BitalinoFalso:
    """Imita BitalinoConLimite: solo responde en los puertos de 'validos'."""

    validos = {"COM7"}

    def __init__(self, puerto, limite_s, detener=None):
        if puerto not in self.validos:
            raise OSError(f"could not open port '{puerto}'")
        self.puerto = puerto
        self.detener = detener
        self.rng = np.random.default_rng(0)
        self.cerrado = False

    def version(self):
        return "BITalino_v5.1 (falso)"

    def start(self, fs, canales):
        pass

    def read(self, n):
        trama = np.zeros((n, 6), dtype=int)
        trama[:, 5] = 512 + self.rng.integers(-3, 4, n)
        return trama

    def stop(self):
        pass

    def close(self):
        self.cerrado = True


def test_conectar_bitalino_automatico_y_recordar_el_puerto(tmp_path):
    api = Api(tmp_path, abrir_bitalino=BitalinoFalso, buscar_puertos=lambda: ["COM3", "COM7"])
    VentanaFalsa(api)
    api.conectar({"simulacion": False, "puerto": None})
    esperar_tarea(api)
    conexion = api.obtener_estado()["conexion"]
    assert conexion["estado"] == "Conectado" and conexion["puerto"] == "COM7"
    assert leer_ajustes(tmp_path)["ultimo_puerto"] == "COM7"
    api.calibrar()
    esperar_tarea(api)
    assert api.obtener_estado()["calibracion"]["estado"] in {"PASS", "WARN"}
    api._cerrar()


def test_puerto_que_no_responde_muestra_el_error(tmp_path):
    api = Api(tmp_path, abrir_bitalino=BitalinoFalso, buscar_puertos=lambda: [])
    VentanaFalsa(api)
    api.conectar({"simulacion": False, "puerto": "COM3"})
    esperar_tarea(api)
    conexion = api.obtener_estado()["conexion"]
    assert conexion["estado"] == "Error"
    assert "no se pudo abrir el puerto" in conexion["detalle"]
    api._cerrar()
