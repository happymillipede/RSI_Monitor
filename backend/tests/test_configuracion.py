"""Pruebas de config.json: creación desde el ejemplo y prioridad de los valores."""

import json

import pytest

from app import almacenamiento
from app.almacenamiento import PARAMETROS_DETECCION, Configuracion


def test_crea_config_desde_el_ejemplo(tmp_path):
    configuracion = Configuracion(tmp_path)

    ruta = tmp_path / almacenamiento.NOMBRE_CONFIG
    ejemplo = almacenamiento.RUTA_CONFIG_EJEMPLO
    assert ruta.exists()
    assert json.loads(ruta.read_text(encoding="utf-8")) == json.loads(ejemplo.read_text(encoding="utf-8"))
    assert configuracion["descansos"]["duracion_fatiga_min"] == 10


def test_null_usa_el_valor_del_original(original, tmp_path):
    configuracion = Configuracion(tmp_path)
    parametros = configuracion.parametros_deteccion(original.constantes)
    for nombre in PARAMETROS_DETECCION:
        assert parametros[nombre] == original.constantes[nombre]


def test_valor_del_usuario_tiene_prioridad(original, tmp_path):
    configuracion = Configuracion(tmp_path)
    configuracion["parametros_deteccion"]["RMS_INCREASE_THRESHOLD"] = 0.3
    configuracion.guardar()

    otra_vez = Configuracion(tmp_path)
    parametros = otra_vez.parametros_deteccion(original.constantes)
    assert parametros["RMS_INCREASE_THRESHOLD"] == 0.3
    assert parametros["MDF_DECREASE_THRESHOLD"] == original.constantes["MDF_DECREASE_THRESHOLD"]


def test_umbrales_sim(original, tmp_path):
    configuracion = Configuracion(tmp_path)
    configuracion["parametros_deteccion"]["RMS_INCREASE_THRESHOLD"] = 0.3
    parametros = configuracion.parametros_deteccion(original.constantes, usar_umbrales_sim=True)
    for nombre in PARAMETROS_DETECCION:
        assert parametros[nombre] == original.constantes["SIM_" + nombre]


def test_agrega_claves_nuevas_del_ejemplo(tmp_path):
    (tmp_path / almacenamiento.NOMBRE_CONFIG).write_text(
        json.dumps({"descansos": {"duracion_fatiga_min": 7}}), encoding="utf-8"
    )
    configuracion = Configuracion(tmp_path)
    assert configuracion["descansos"]["duracion_fatiga_min"] == 7
    assert configuracion["descansos"]["plantillas_iniciales"]
    assert "parametros_deteccion" in configuracion.datos


def test_config_danado_se_rehace(tmp_path):
    (tmp_path / almacenamiento.NOMBRE_CONFIG).write_text("{ esto no es json", encoding="utf-8")
    configuracion = Configuracion(tmp_path)
    assert configuracion["descansos"]["duracion_fatiga_min"] == 10
    assert (tmp_path / (almacenamiento.NOMBRE_CONFIG + ".dañado")).exists()


def test_escenario_null_usa_sim_scenario(original, tmp_path):
    configuracion = Configuracion(tmp_path)
    assert configuracion.escenario_simulacion(original.constantes) == original.constantes["SIM_SCENARIO"]


def test_poner_parametro_igual_al_original_queda_null(tmp_path, original):
    configuracion = Configuracion(tmp_path)
    constantes = original.constantes
    configuracion.poner_parametro("RMS_INCREASE_THRESHOLD", 0.30, constantes)
    configuracion.poner_parametro("MDF_DECREASE_THRESHOLD", constantes["MDF_DECREASE_THRESHOLD"], constantes)
    configuracion.guardar()

    guardado = json.loads(configuracion.ruta.read_text(encoding="utf-8"))["parametros_deteccion"]
    assert guardado["RMS_INCREASE_THRESHOLD"] == 0.30
    assert guardado["MDF_DECREASE_THRESHOLD"] is None
    parametros = Configuracion(tmp_path).parametros_deteccion(constantes)
    assert parametros["RMS_INCREASE_THRESHOLD"] == 0.30

    configuracion.poner_parametro("RMS_INCREASE_THRESHOLD", None, constantes)  # "Restaurar"
    assert configuracion.parametros_deteccion(constantes)["RMS_INCREASE_THRESHOLD"] == constantes["RMS_INCREASE_THRESHOLD"]


def test_poner_parametro_fuera_de_rango(tmp_path, original):
    configuracion = Configuracion(tmp_path)
    with pytest.raises(ValueError, match="TREND_INTERVAL_S"):
        configuracion.poner_parametro("TREND_INTERVAL_S", 0, original.constantes)
    with pytest.raises(ValueError):
        configuracion.poner_parametro("MDF_DECREASE_THRESHOLD", 1.5, original.constantes)
