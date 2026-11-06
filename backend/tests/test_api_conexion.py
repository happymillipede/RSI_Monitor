"""
Panel de conexión por la API, con un BITalino falso (sin hardware):
Reconectar a un puerto, Detectar automáticamente, Encender con el BITalino ya
conectado y elegir un puerto cuando la conexión se corta midiendo.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import crear_app
from app.servicio import crear_servicio
from tests.test_api import PUERTO, esperar

COLUMNAS_TRAMA = 6


class BitalinoFalso:
    """Imita BitalinoConLimite. Solo responde en los puertos de 'puertos_validos'."""

    def __init__(self, fabrica, puerto, limite_s, detener=None):
        if puerto not in fabrica.puertos_validos:
            raise OSError(f"could not open port '{puerto}'")
        self.fabrica = fabrica
        self.puerto = puerto
        self.detener = detener
        self.lecturas = 0
        self.rng = np.random.default_rng(0)

    def version(self):
        return "BITalino_v5.1 (falso)"

    def start(self, fs, canales):
        pass

    def read(self, n):
        self.lecturas += 1
        if self.fabrica.cortar_despues_de and self.lecturas > self.fabrica.cortar_despues_de:
            raise OSError("The computer lost communication with the device.")
        trama = np.zeros((n, COLUMNAS_TRAMA), dtype=int)
        trama[:, 5] = 512 + self.rng.integers(-20, 20, n)
        return trama

    def stop(self):
        pass

    def close(self):
        self.fabrica.cerrados.append(self.puerto)


class FabricaFalsa:
    """Reemplaza a BitalinoConLimite en el servicio y anota cada BITalino que se abre."""

    def __init__(self, puertos_validos):
        self.puertos_validos = set(puertos_validos)
        self.cortar_despues_de = None
        self.abiertos = []
        self.cerrados = []

    def __call__(self, puerto, limite_s, detener=None):
        dispositivo = BitalinoFalso(self, puerto, limite_s, detener)
        self.abiertos.append(dispositivo)
        return dispositivo


@pytest.fixture
def servicio(tmp_path):
    servicio = crear_servicio(carpeta_datos=tmp_path, en_docker=False)
    servicio.abrir_bitalino = FabricaFalsa(["COM7"])
    servicio.buscar_puertos = lambda: ["COM3", "COM7"]
    return servicio


@pytest.fixture
def cliente(servicio):
    with TestClient(crear_app(servicio, PUERTO)) as cliente:
        yield cliente


def conexion(estado):
    return estado["conexion"]


def test_reconectar_a_un_puerto_y_encender_lo_usa(cliente, servicio):
    cliente.post("/api/conexion/reconectar", json={"puerto": "COM7"})
    estado = esperar(cliente, lambda e: conexion(e)["estado"] == "Conectado")
    assert conexion(estado)["puerto"] == "COM7"
    assert conexion(estado)["version"] == "BITalino_v5.1 (falso)"
    assert servicio.configuracion["conexion"]["ultimo_puerto"] == "COM7"

    cliente.post("/api/medicion/encender", json={"modo": "real"})
    esperar(cliente, lambda e: e["ultimo_bloque"] is not None)
    assert len(servicio.abrir_bitalino.abiertos) == 1  # usó el que ya estaba conectado
    cliente.post("/api/medicion/apagar")
    esperar(cliente, lambda e: not e["medicion"]["encendida"])
    assert servicio.abrir_bitalino.cerrados == ["COM7"]


def test_puerto_que_no_responde_muestra_el_error_en_palabras_simples(cliente):
    cliente.post("/api/conexion/reconectar", json={"puerto": "COM3"})
    estado = esperar(cliente, lambda e: conexion(e)["estado"] == "Error")
    assert "no se pudo abrir el puerto" in conexion(estado)["detalle"]


def test_detectar_automaticamente(cliente, servicio):
    cliente.post("/api/conexion/reconectar", json={"puerto": None})
    estado = esperar(cliente, lambda e: conexion(e)["estado"] == "Conectado")
    assert conexion(estado)["puerto"] == "COM7"
    probados = [d.puerto for d in servicio.abrir_bitalino.abiertos]
    assert probados == ["COM7"]  # COM3 y el PUERTO del original fallaron antes


def test_detectar_sin_bitalino_avisa(cliente, servicio):
    servicio.abrir_bitalino.puertos_validos = set()
    cliente.post("/api/conexion/reconectar", json={})
    estado = esperar(cliente, lambda e: conexion(e)["estado"] == "Error")
    assert "COM3" in conexion(estado)["detalle"] and "COM7" in conexion(estado)["detalle"]


def test_elegir_puerto_cuando_se_corta_midiendo(cliente, servicio):
    fabrica = servicio.abrir_bitalino
    fabrica.cortar_despues_de = 3
    servicio.configuracion["conexion"]["espera_inicial_s"] = 30  # sin elegir puerto, esperaría 30 s

    cliente.post("/api/medicion/encender", json={"modo": "real"})
    esperar(cliente, lambda e: conexion(e)["estado"] == "Conectado")
    fabrica.puertos_validos = {"COM8"}  # el BITalino "cambió" de puerto
    estado = esperar(cliente, lambda e: conexion(e)["estado"] == "Buscando" and "Nuevo intento" in conexion(e)["detalle"])
    assert estado["medicion"]["encendida"] is True

    fabrica.cortar_despues_de = None
    assert cliente.post("/api/conexion/reconectar", json={"puerto": "COM8"}).status_code == 200
    estado = esperar(cliente, lambda e: conexion(e)["estado"] == "Conectado")
    assert conexion(estado)["puerto"] == "COM8"
    assert servicio.configuracion["conexion"]["ultimo_puerto"] == "COM8"

    # Ya conectado y midiendo: para cambiar de puerto hay que apagar.
    assert cliente.post("/api/conexion/reconectar", json={"puerto": "COM7"}).status_code == 409
    cliente.post("/api/medicion/apagar")
    esperar(cliente, lambda e: not e["medicion"]["encendida"])


def test_reconectar_en_simulacion_no_corresponde(cliente):
    cliente.post("/api/medicion/encender", json={"modo": "simulacion", "velocidad": 0, "escenario": "normal"})
    assert cliente.post("/api/conexion/reconectar", json={"puerto": "COM7"}).status_code == 409
    cliente.post("/api/medicion/apagar")
    esperar(cliente, lambda e: not e["medicion"]["encendida"])


def test_reconectar_en_docker_no_se_puede(tmp_path):
    with TestClient(crear_app(crear_servicio(carpeta_datos=tmp_path, en_docker=True), PUERTO)) as cliente:
        respuesta = cliente.post("/api/conexion/reconectar", json={"puerto": "COM7"})
        assert respuesta.status_code == 409
        assert "Docker" in respuesta.json()["detail"]
