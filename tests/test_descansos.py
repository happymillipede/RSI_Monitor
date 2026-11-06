"""Descansos: flujo de la alerta, historial y plantillas."""

import json
from datetime import datetime, timedelta

import pytest

from nucleo import rutas
from nucleo.configuracion import Configuracion
from uso.descansos import (
    NOMBRE_ARCHIVO,
    NOMBRE_DESCANSO_FATIGA,
    ORIGEN_FATIGA,
    ORIGEN_MANUAL,
    GestorDescansos,
    PlantillasDescanso,
)


class AhoraFalso:
    def __init__(self):
        self.momento = datetime(2026, 11, 6, 10, 0, 0)

    def __call__(self):
        return self.momento

    def avanzar(self, segundos):
        self.momento += timedelta(seconds=segundos)


class MedicionFalsa:
    """Registra las órdenes que el gestor le da al hilo de medición."""

    def __init__(self):
        self.ordenes = []

    def pausar_alertas(self, pausar):
        self.ordenes.append(("pausar", pausar))

    def rearmar_alerta(self):
        self.ordenes.append(("rearmar", None))


@pytest.fixture
def ahora():
    return AhoraFalso()


@pytest.fixture
def gestor(tmp_path, ahora):
    gestor = GestorDescansos(tmp_path, ahora=ahora)
    gestor.conectar_medicion(MedicionFalsa())
    return gestor


def test_flujo_alerta_pendiente_aceptar_descanso_rearme(gestor, ahora, tmp_path):
    medicion = gestor.medicion

    assert gestor.recibir_alerta() is True
    assert gestor.alerta_pendiente
    assert gestor.recibir_alerta() is False  # no se duplica mientras está pendiente

    descanso = gestor.aceptar_alerta(10)
    assert not gestor.alerta_pendiente
    assert gestor.en_descanso()
    assert descanso.origen == ORIGEN_FATIGA and descanso.nombre == NOMBRE_DESCANSO_FATIGA
    assert medicion.ordenes == [("pausar", True)]
    assert gestor.recibir_alerta() is False  # durante el descanso tampoco

    ahora.avanzar(4 * 60)
    assert gestor.segundos_restantes() == 6 * 60
    assert not gestor.termino_el_tiempo()
    ahora.avanzar(6 * 60)
    assert gestor.termino_el_tiempo()

    gestor.terminar(completado=True)
    assert not gestor.en_descanso()
    assert medicion.ordenes == [("pausar", True), ("pausar", False), ("rearmar", None)]
    assert gestor.recibir_alerta() is True  # rearmada

    guardado = json.loads((tmp_path / NOMBRE_ARCHIVO).read_text(encoding="utf-8"))
    assert guardado == [
        {
            "nombre": NOMBRE_DESCANSO_FATIGA,
            "origen": ORIGEN_FATIGA,
            "inicio": "2026-11-06T10:00:00",
            "fin": "2026-11-06T10:10:00",
            "duracion_planeada_min": 10,
            "duracion_real_min": 10,
            "completado": True,
        }
    ]


def test_terminar_antes_queda_como_no_completado(gestor, ahora):
    gestor.iniciar_manual(15, "Café")
    ahora.avanzar(90)
    descanso = gestor.terminar(completado=False)
    registro = gestor.historial[-1]
    assert descanso.nombre == "Café"
    assert registro["origen"] == ORIGEN_MANUAL
    assert registro["duracion_planeada_min"] == 15
    assert registro["duracion_real_min"] == 1.5
    assert registro["completado"] is False


def test_descanso_manual_no_empieza_con_alerta_pendiente_ni_durante_otro(gestor):
    gestor.recibir_alerta()
    assert gestor.iniciar_manual(5) is None
    gestor.aceptar_alerta(10)
    assert gestor.iniciar_manual(5) is None


def test_descanso_manual_valida_la_duracion(gestor):
    with pytest.raises(ValueError):
        gestor.iniciar_manual(0)
    assert not gestor.en_descanso()


def test_encender_durante_un_descanso_pausa_la_nueva_medicion(tmp_path, ahora):
    gestor = GestorDescansos(tmp_path, ahora=ahora)
    gestor.iniciar_manual(5)  # medición apagada
    medicion = MedicionFalsa()
    gestor.conectar_medicion(medicion)
    assert medicion.ordenes == [("pausar", True)]


def test_total_del_dia_e_historial_persistente(tmp_path, ahora):
    gestor = GestorDescansos(tmp_path, ahora=ahora)
    gestor.iniciar_manual(5)
    ahora.avanzar(5 * 60)
    gestor.terminar(True)
    ahora.avanzar(3600)
    gestor.iniciar_manual(15, "Café")
    ahora.avanzar(3 * 60)
    gestor.terminar(False)
    ahora.avanzar(24 * 3600)  # al día siguiente
    gestor.iniciar_manual(5)
    ahora.avanzar(60)
    gestor.terminar(False)

    assert gestor.minutos_del_dia(datetime(2026, 11, 6).date()) == 8
    assert len(gestor.descansos_del_dia()) == 1  # hoy = 7 de noviembre

    otro = GestorDescansos(tmp_path, ahora=ahora)
    assert len(otro.historial) == 3


def test_plantillas_crear_editar_borrar(tmp_path):
    configuracion = Configuracion(tmp_path, rutas.RAIZ_PROYECTO)
    plantillas = PlantillasDescanso(configuracion)
    iniciales = [p["nombre"] for p in plantillas.lista()]
    assert iniciales == ["Pausa activa", "Café"]

    plantillas.agregar("  Estirar  ", 3)
    assert plantillas.lista()[-1] == {"nombre": "Estirar", "duracion_min": 3}
    plantillas.editar(0, "Pausa activa", 7)
    plantillas.borrar(1)

    # Quedan guardadas en config.json
    otra = PlantillasDescanso(Configuracion(tmp_path, rutas.RAIZ_PROYECTO))
    assert otra.lista() == [
        {"nombre": "Pausa activa", "duracion_min": 7},
        {"nombre": "Estirar", "duracion_min": 3},
    ]


def test_plantillas_validan_nombre_duracion_y_repetidos(tmp_path):
    plantillas = PlantillasDescanso(Configuracion(tmp_path, rutas.RAIZ_PROYECTO))
    with pytest.raises(ValueError, match="nombre"):
        plantillas.agregar("   ", 5)
    with pytest.raises(ValueError, match="minutos"):
        plantillas.agregar("Larga", 1000)
    with pytest.raises(ValueError, match="Ya existe"):
        plantillas.agregar("café", 10)
    plantillas.editar(1, "Café", 20)  # editar sin cambiar el nombre está bien
    assert plantillas.lista()[1]["duracion_min"] == 20
