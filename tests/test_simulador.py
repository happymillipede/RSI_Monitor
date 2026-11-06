"""Pruebas del BITalino simulado (forma de la trama y ritmo real)."""

import numpy as np
import pytest

from nucleo.simulador import COLUMNA_EMG, DispositivoSimulado


class RelojFalso:
    def __init__(self):
        self.ahora = 100.0
        self.esperas = []

    def __call__(self):
        return self.ahora

    def dormir(self, segundos):
        self.esperas.append(segundos)
        self.ahora += segundos


def test_trama_como_bitalino():
    dispositivo = DispositivoSimulado("normal", 1000, 1, velocidad=None)
    dispositivo.start(1000, [0])
    trama = dispositivo.read(1000)

    assert trama.shape == (1000, 6)
    assert trama.dtype.kind == "i"
    assert list(trama[:17, 0]) == list(range(16)) + [0]
    assert np.all((trama[:, COLUMNA_EMG] >= 0) & (trama[:, COLUMNA_EMG] <= 1023))
    assert np.all(trama[:, 1:5] == 0)


def test_read_sin_start_falla():
    dispositivo = DispositivoSimulado("normal", 1000, 1, velocidad=None)
    with pytest.raises(Exception):
        dispositivo.read(10)


@pytest.mark.parametrize("velocidad, espera_esperada", [(1, 1.0), (10, 0.1)])
def test_entrega_a_ritmo_real(velocidad, espera_esperada):
    reloj = RelojFalso()
    dispositivo = DispositivoSimulado("normal", 1000, 1, velocidad, reloj=reloj, dormir=reloj.dormir)
    dispositivo.start(1000, [0])
    for _ in range(3):
        dispositivo.read(1000)

    assert reloj.esperas == pytest.approx([espera_esperada] * 3)


def test_escenario_invalido():
    with pytest.raises(ValueError):
        DispositivoSimulado("otro", 1000, 1)
