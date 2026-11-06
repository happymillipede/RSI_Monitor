"""
Escenarios de la simulación y ciclo de medición.

Hallazgo (señal simulada de 1000 s, semilla 42):
- fatigue_test con umbrales SIM_*: alerta a los ~17,5 s.
- normal con umbrales normales: no alerta.
- fatigue_test con umbrales NORMALES: no alerta. La MDF baja ~40 %, pero el RMS sube
  solo ~3 % en promedio (la señal de baja frecuencia tiene menos potencia y la
  amplitud x1,5 casi solo la compensa), lejos del +20 % durante 5 s seguidos.
- normal con umbrales SIM_*: alerta una vez a los ~381 s (falso positivo por azar:
  +5 % de RMS y -1 % de MDF durante un solo intervalo es una condición muy laxa).
"""

import csv

import numpy as np
import pytest

from nucleo.adquisicion import (
    CALIBRANDO,
    CONECTANDO,
    DESCONECTADO,
    ENCABEZADO_CSV,
    ERROR,
    MIDIENDO,
    SesionMedicion,
)
from tests.utilidades import parametros_del_original, simular


def test_fatigue_test_con_umbrales_sim_dispara(original, tmp_path):
    _, oyente = simular(original, tmp_path, "fatigue_test", 60, sim=True)
    assert len(oyente.alertas) == 1


def test_normal_con_umbrales_normales_no_dispara(original, tmp_path):
    _, oyente = simular(original, tmp_path, "normal", 300)
    assert oyente.alertas == []


def test_fatigue_test_con_umbrales_normales_no_dispara(original, tmp_path):
    """Documenta el hallazgo de arriba: con +20 % de RMS el escenario no alcanza a alertar."""
    _, oyente = simular(original, tmp_path, "fatigue_test", 120)
    assert oyente.alertas == []


def test_estados_y_csv_de_la_sesion(original, tmp_path):
    sesion, oyente = simular(original, tmp_path, "normal", 10)

    assert oyente.estados == [CONECTANDO, CALIBRANDO, MIDIENDO, DESCONECTADO]
    assert sesion.ruta_csv.name.startswith("prueba_")
    with open(sesion.ruta_csv, newline="", encoding="utf-8") as archivo:
        filas = list(csv.reader(archivo))
    assert filas[0] == ENCABEZADO_CSV
    # 10 bloques de 1 s = 10 intervalos; el último se cierra al detener (línea 443).
    assert len(filas) == 1 + 10
    assert len(oyente.bloques[-1].muestras_recientes) == 8


class DispositivoQueFalla:
    """Entrega dos bloques y después falla, como un BITalino que se desconecta."""

    def __init__(self, original):
        self.original = original
        self.lecturas = 0
        self.detenido = False
        self.cerrado = False

    def start(self, fs, canales):
        pass

    def read(self, n):
        self.lecturas += 1
        if self.lecturas > 2:
            raise Exception("The computer lost communication with the device.")

        trama = np.zeros((n, 6), dtype=int)
        trama[:, 5] = 512 + (np.arange(n) % 7)
        return trama

    def stop(self):
        self.detenido = True

    def close(self):
        self.cerrado = True


def test_stop_se_llama_aunque_falle_la_lectura(original, tmp_path):
    dispositivo = DispositivoQueFalla(original)
    sesion = SesionMedicion(
        original,
        parametros_del_original(original.constantes),
        lambda detener, avisar: dispositivo,
        tmp_path,
        "prueba",
    )
    with pytest.raises(Exception, match="lost communication"):
        sesion.ejecutar()

    assert dispositivo.detenido and dispositivo.cerrado
    assert sesion.estado == ERROR


def test_no_deja_csv_vacio_si_no_hay_dispositivo(original, tmp_path):
    def abrir_que_falla(detener, avisar):
        raise RuntimeError("no hay BITalino")

    sesion = SesionMedicion(
        original, parametros_del_original(original.constantes), abrir_que_falla, tmp_path, "prueba"
    )
    with pytest.raises(RuntimeError):
        sesion.ejecutar()

    assert sesion.estado == ERROR
    assert list(tmp_path.iterdir()) == []
