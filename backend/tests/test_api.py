"""
API REST y WebSocket con el TestClient de FastAPI, en modo simulación (sin hardware).

Las mediciones usan velocidad 0 (sin esperar tiempo real) salvo cuando se lee el
WebSocket, donde se usa x10 para no llenar la cola de mensajes.
"""

import csv
import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import crear_app
from app.servicio import EN_DESCANSO, RIESGO_FATIGA, TEXTO_DOCKER, crear_servicio

PUERTO = 8000
LIMITE_ESPERA_S = 30
PAUSA_S = 0.02

SIMULACION_RAPIDA = {"modo": "simulacion", "escenario": "fatigue_test", "velocidad": 0, "umbrales_sim": True}


class AhoraFalso:
    def __init__(self):
        self.momento = datetime(2026, 11, 6, 10, 0, 0)

    def __call__(self):
        return self.momento

    def avanzar(self, segundos):
        self.momento += timedelta(seconds=segundos)


def abrir_cliente(servicio):
    return TestClient(crear_app(servicio, PUERTO))


@pytest.fixture
def cliente(tmp_path):
    with abrir_cliente(crear_servicio(carpeta_datos=tmp_path, en_docker=False)) as cliente:
        yield cliente


def esperar(cliente, condicion):
    """Consulta /api/estado hasta que condicion(estado) sea verdadera."""
    fin = time.monotonic() + LIMITE_ESPERA_S
    while time.monotonic() < fin:
        estado = cliente.get("/api/estado").json()
        if condicion(estado):
            return estado
        time.sleep(PAUSA_S)
    raise AssertionError("Se acabó el tiempo de espera")


def apagar(cliente):
    cliente.post("/api/medicion/apagar")
    return esperar(cliente, lambda estado: not estado["medicion"]["encendida"])


def test_estado_inicial(cliente):
    estado = cliente.get("/api/estado").json()
    assert estado["tipo"] == "estado"
    assert estado["estado_app"] == "Apagado"
    assert estado["medicion"]["encendida"] is False
    assert estado["alerta"]["pendiente"] is False
    assert estado["alerta"]["texto"] == "Riesgo de fatiga muscular, descanse 10 minutos"
    assert estado["parametros"]["TREND_WINDOW_S"] == 30
    assert estado["conexion"]["estado"] == "Desconectado"


def test_websocket_envia_la_foto_y_el_tiempo_real(cliente):
    with cliente.websocket_connect("/ws") as ws:
        assert ws.receive_json()["tipo"] == "estado"
        cliente.post("/api/medicion/encender", json={"modo": "simulacion", "escenario": "normal", "velocidad": 10})

        tipos = set()
        fin = time.monotonic() + LIMITE_ESPERA_S
        while not {"bloque", "tendencia", "reloj"} <= tipos and time.monotonic() < fin:
            mensaje = ws.receive_json()
            tipos.add(mensaje["tipo"])
            if mensaje["tipo"] == "bloque":
                assert "BITALINO — ADQUISICIÓN Y PROCESAMIENTO" in mensaje["bloque"]["texto_panel"]
                assert len(mensaje["bloque"]["muestras_recientes"]) == 8
        assert {"estado", "conexion", "bloque", "tendencia", "reloj"} <= tipos
    apagar(cliente)


def test_la_medicion_guarda_el_csv_como_el_original(cliente):
    cliente.post("/api/medicion/encender", json={**SIMULACION_RAPIDA, "escenario": "normal"})
    esperar(cliente, lambda estado: len(estado["tendencia"]) >= 5)
    estado = apagar(cliente)

    with open(estado["medicion"]["ruta_csv"], encoding="utf-8") as archivo:
        filas = list(csv.reader(archivo))
    assert filas[0] == ["Time (s)", "Mean RMS (ADC)", "Median MDF (Hz)"]
    assert len(filas) - 1 >= 5
    assert "EMG_simulated_features_" in estado["medicion"]["ruta_csv"]
    assert estado["calibracion"]["linea_base"] is not None


def test_flujo_alerta_aceptar_descanso_rearme(cliente):
    cliente.post("/api/medicion/encender", json=SIMULACION_RAPIDA)
    estado = esperar(cliente, lambda estado: estado["alerta"]["pendiente"])
    assert estado["estado_app"] == RIESGO_FATIGA

    # Recargar la página: la foto trae la alerta pendiente y la tendencia.
    with cliente.websocket_connect("/ws") as ws:
        foto = ws.receive_json()
    assert foto["alerta"]["pendiente"] is True
    assert foto["tendencia"]

    # Con la alerta pendiente no se puede encender otra vez ni tomar otro descanso.
    assert cliente.post("/api/medicion/encender", json=SIMULACION_RAPIDA).status_code == 409
    assert cliente.post("/api/descanso/iniciar", json={"minutos": 5}).status_code == 409

    estado = cliente.post("/api/alerta/aceptar").json()
    assert estado["alerta"]["pendiente"] is False
    assert estado["descanso"]["activo"] is True
    assert estado["descanso"]["origen"] == "fatiga"
    assert estado["estado_app"] == EN_DESCANSO
    assert estado["reloj"]["corriendo"] is False
    assert cliente.post("/api/alerta/aceptar").status_code == 409

    estado = cliente.post("/api/descanso/terminar").json()
    assert estado["descanso"]["activo"] is False

    # Al terminar el descanso la alerta se rearma (la señal sigue con fatiga).
    esperar(cliente, lambda estado: estado["alerta"]["pendiente"])
    apagar(cliente)
    # Apagar no borra la alerta: sigue hasta que se acepte o se cierre la app.
    assert cliente.get("/api/estado").json()["alerta"]["pendiente"] is True

    historial = cliente.get("/api/descansos/historial").json()
    assert historial["cantidad_hoy"] == 1
    assert historial["historial"][0]["origen"] == "fatiga"
    assert historial["historial"][0]["completado"] is False


def test_el_descanso_termina_solo_y_rearma(tmp_path):
    ahora = AhoraFalso()
    servicio = crear_servicio(carpeta_datos=tmp_path, en_docker=False, ahora=ahora)
    with abrir_cliente(servicio) as cliente:
        cliente.post("/api/descanso/iniciar", json={"plantilla": 1})  # "Café, 15 min"
        estado = cliente.get("/api/estado").json()
        assert estado["descanso"]["nombre"] == "Café"
        assert estado["descanso"]["segundos_restantes"] == 15 * 60

        ahora.avanzar(15 * 60)
        servicio.cada_segundo()
        assert cliente.get("/api/estado").json()["descanso"]["activo"] is False
        assert cliente.get("/api/descansos/historial").json()["historial"][0]["completado"] is True


def test_descanso_manual_valida_la_duracion(cliente):
    assert cliente.post("/api/descanso/iniciar", json={"minutos": 1000}).status_code == 400
    assert cliente.post("/api/descanso/iniciar", json={}).status_code == 400
    assert cliente.post("/api/descanso/iniciar", json={"plantilla": 99}).status_code == 404
    assert cliente.post("/api/descanso/terminar").status_code == 409


def test_plantillas(cliente):
    plantillas = cliente.get("/api/plantillas").json()["plantillas"]
    assert [p["nombre"] for p in plantillas] == ["Pausa activa", "Café"]

    cliente.post("/api/plantillas", json={"nombre": "Estirar", "duracion_min": 3})
    cliente.put("/api/plantillas/0", json={"nombre": "Pausa activa", "duracion_min": 7})
    plantillas = cliente.delete("/api/plantillas/1").json()["plantillas"]
    assert plantillas == [{"nombre": "Pausa activa", "duracion_min": 7}, {"nombre": "Estirar", "duracion_min": 3}]

    assert cliente.post("/api/plantillas", json={"nombre": " ", "duracion_min": 3}).status_code == 400
    assert cliente.post("/api/plantillas", json={"nombre": "estirar", "duracion_min": 3}).status_code == 400
    assert cliente.delete("/api/plantillas/9").status_code == 404


def test_configuracion(cliente):
    config = cliente.get("/api/config").json()
    rms = next(p for p in config["parametros"] if p["nombre"] == "RMS_INCREASE_THRESHOLD")
    assert rms["valor"] == rms["original"] == 0.20
    assert rms["personalizado"] is False

    config = cliente.put("/api/config", json={"parametros": {"RMS_INCREASE_THRESHOLD": 0.3}, "duracion_fatiga_min": 15}).json()
    rms = next(p for p in config["parametros"] if p["nombre"] == "RMS_INCREASE_THRESHOLD")
    assert rms["valor"] == 0.3 and rms["personalizado"] is True
    assert cliente.get("/api/estado").json()["alerta"]["texto"] == "Riesgo de fatiga muscular, descanse 15 minutos"

    config = cliente.put("/api/config", json={"restaurar": True}).json()
    assert all(not p["personalizado"] for p in config["parametros"])

    assert cliente.put("/api/config", json={"parametros": {"TREND_INTERVAL_S": 0}}).status_code == 400
    assert cliente.put("/api/config", json={"parametros": {"OTRO": 1}}).status_code == 400
    assert cliente.put("/api/config", json={"duracion_fatiga_min": 0}).status_code == 400


def test_encender_dos_veces_y_apagar_apagado(cliente):
    assert cliente.post("/api/medicion/apagar").status_code == 409
    cliente.post("/api/medicion/encender", json={**SIMULACION_RAPIDA, "escenario": "normal"})
    assert cliente.post("/api/medicion/encender", json=SIMULACION_RAPIDA).status_code == 409
    apagar(cliente)


def test_otra_pagina_web_no_puede_usar_la_api(cliente):
    malo = {"origin": "http://pagina-mala.example"}
    assert cliente.post("/api/descanso/iniciar", json={"minutos": 5}, headers=malo).status_code == 403
    with pytest.raises(WebSocketDisconnect):
        with cliente.websocket_connect("/ws", headers=malo) as ws:
            ws.receive_json()

    for origen in ("http://localhost:3000", f"http://127.0.0.1:{PUERTO}"):
        respuesta = cliente.post("/api/plantillas", json={"nombre": origen, "duracion_min": 3}, headers={"origin": origen})
        assert respuesta.status_code == 200
    # El frontend de desarrollo (next dev) puede leer las respuestas (CORS).
    respuesta = cliente.get("/api/estado", headers={"origin": "http://localhost:3000"})
    assert respuesta.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_en_docker_solo_hay_simulacion(tmp_path):
    with abrir_cliente(crear_servicio(carpeta_datos=tmp_path, en_docker=True)) as cliente:
        estado = cliente.get("/api/estado").json()
        assert estado["conexion"]["en_docker"] is True
        assert estado["conexion"]["detalle"] == TEXTO_DOCKER
        assert estado["medicion"]["modo_preferido"] == "simulacion"

        respuesta = cliente.post("/api/medicion/encender", json={"modo": "real"})
        assert respuesta.status_code == 409
        assert "Docker" in respuesta.json()["detail"]
        assert cliente.get("/api/puertos").json() == {"detectados": [], "todos": []}


def test_pagina_principal(cliente):
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert "RSI Monitor" in respuesta.text
