"""Reloj de uso: corre solo midiendo, se pausa en los descansos, se guarda y cambia de día."""

import json
from datetime import date

from app.almacenamiento import NOMBRE_DESCANSOS
from app.uso.reloj_uso import MAXIMO_SALTO_S, RelojUso, formato_reloj
from tests.utilidades import archivo_descansos


class TiempoFalso:
    """Reloj y fecha que avanzan solo cuando la prueba lo pide."""

    def __init__(self, dia=date(2026, 11, 6)):
        self.segundos = 1000.0
        self.dia = dia

    def reloj(self):
        return self.segundos

    def hoy(self):
        return self.dia

    def avanzar(self, reloj_uso, segundos):
        """Avanza de a 1 s llamando a tick(), como la tarea de cada segundo del servidor."""
        for _ in range(int(segundos)):
            self.segundos += 1
            reloj_uso.tick()


def crear_reloj(carpeta, tiempo, guardar_cada_s=30):
    return RelojUso(archivo_descansos(carpeta), guardar_cada_s, reloj=tiempo.reloj, hoy=tiempo.hoy)


def test_solo_corre_mientras_se_mide(tmp_path):
    tiempo = TiempoFalso()
    reloj = crear_reloj(tmp_path, tiempo)
    tiempo.avanzar(reloj, 10)  # apagado
    assert reloj.segundos_hoy() == 0

    reloj.empezar_medicion()
    tiempo.avanzar(reloj, 25)
    reloj.terminar_medicion()
    tiempo.avanzar(reloj, 10)  # apagado otra vez
    assert reloj.segundos_hoy() == 25
    assert reloj.segundos_sesion == 25


def test_se_pausa_durante_el_descanso(tmp_path):
    tiempo = TiempoFalso()
    reloj = crear_reloj(tmp_path, tiempo)
    reloj.empezar_medicion()
    tiempo.avanzar(reloj, 10)
    reloj.empezar_descanso()
    tiempo.avanzar(reloj, 300)
    reloj.terminar_descanso()
    tiempo.avanzar(reloj, 5)
    assert reloj.segundos_hoy() == 15
    assert reloj.segundos_sesion == 15


def test_la_sesion_vuelve_a_cero_y_el_dia_se_acumula(tmp_path):
    tiempo = TiempoFalso()
    reloj = crear_reloj(tmp_path, tiempo)
    reloj.empezar_medicion()
    tiempo.avanzar(reloj, 20)
    reloj.terminar_medicion()
    reloj.empezar_medicion()
    tiempo.avanzar(reloj, 7)
    assert reloj.segundos_sesion == 7
    assert reloj.segundos_hoy() == 27


def test_el_total_del_dia_se_guarda_y_se_recupera(tmp_path):
    tiempo = TiempoFalso()
    reloj = crear_reloj(tmp_path, tiempo)
    reloj.empezar_medicion()
    tiempo.avanzar(reloj, 42)
    reloj.terminar_medicion()

    datos = json.loads((tmp_path / NOMBRE_DESCANSOS).read_text(encoding="utf-8"))
    assert datos["uso_diario"] == {"2026-11-06": 42.0}

    # Al abrir la app de nuevo el mismo día, sigue sumando desde ahí.
    otro = crear_reloj(tmp_path, tiempo)
    assert otro.segundos_hoy() == 42
    otro.empezar_medicion()
    tiempo.avanzar(otro, 8)
    assert otro.segundos_hoy() == 50


def test_guarda_cada_cierto_tiempo_mientras_mide(tmp_path):
    tiempo = TiempoFalso()
    reloj = crear_reloj(tmp_path, tiempo, guardar_cada_s=30)
    reloj.empezar_medicion()
    tiempo.avanzar(reloj, 29)
    assert not (tmp_path / NOMBRE_DESCANSOS).exists()
    tiempo.avanzar(reloj, 1)
    assert (tmp_path / NOMBRE_DESCANSOS).exists()


def test_vuelve_a_cero_cuando_cambia_el_dia(tmp_path):
    tiempo = TiempoFalso(dia=date(2026, 11, 6))
    reloj = crear_reloj(tmp_path, tiempo)
    reloj.empezar_medicion()
    tiempo.avanzar(reloj, 60)
    tiempo.dia = date(2026, 11, 7)
    assert reloj.segundos_hoy() == 0
    tiempo.avanzar(reloj, 10)
    assert reloj.segundos_hoy() == 10
    assert reloj.segundos_por_dia["2026-11-06"] == 60
    assert reloj.segundos_sesion == 70  # la sesión sigue aunque pase la medianoche


def test_no_cuenta_el_tiempo_con_el_computador_suspendido(tmp_path):
    tiempo = TiempoFalso()
    reloj = crear_reloj(tmp_path, tiempo)
    reloj.empezar_medicion()
    tiempo.avanzar(reloj, 5)
    tiempo.segundos += MAXIMO_SALTO_S + 3600  # una hora sin tick()
    reloj.tick()
    tiempo.avanzar(reloj, 5)
    assert reloj.segundos_hoy() == 10


def test_archivo_dañado_parte_de_cero(tmp_path):
    (tmp_path / NOMBRE_DESCANSOS).write_text("{no es json", encoding="utf-8")
    reloj = crear_reloj(tmp_path, TiempoFalso())
    assert reloj.segundos_hoy() == 0
    assert (tmp_path / (NOMBRE_DESCANSOS + ".dañado")).exists()


def test_formato_reloj():
    assert formato_reloj(0) == "00:00"
    assert formato_reloj(75.9) == "01:15"
    assert formato_reloj(3725) == "1:02:05"
