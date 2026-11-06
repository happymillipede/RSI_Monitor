"""
Utilidades comunes de las pruebas (pytest carga este archivo solo).

- original: el código original cargado con el cargador ast.
Las funciones de ayuda para simular están en tests/utilidades.py.
"""

import pytest

from nucleo.cargador_original import cargar_original


@pytest.fixture(scope="session")
def original():
    return cargar_original()
