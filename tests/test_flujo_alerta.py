"""
Flujo completo con la medición simulada:
alerta -> pendiente -> Aceptar -> descanso (sin alertas) -> fin -> rearme -> nueva alerta.
"""

from datetime import datetime, timedelta

from nucleo.adquisicion import Oyente, SesionMedicion
from nucleo.simulador import DispositivoSimulado
from tests.utilidades import parametros_del_original
from uso.descansos import ORIGEN_FATIGA, GestorDescansos

INTERVALOS_DE_DESCANSO = 10
DURACION_S = 80


class OyenteFlujo(Oyente):
    """Hace lo mismo que la ventana: avisa al gestor y acepta la alerta enseguida."""

    def __init__(self, gestor, ahora):
        self.gestor = gestor
        self.ahora = ahora
        self.sesion = None
        self.alertas = []
        self.alertas_mostradas = 0
        self.intervalos_en_descanso = 0
        self.alertas_en_descanso = 0

    def al_cerrar_intervalo(self, resumen, linea_base):
        self.ahora.momento += timedelta(seconds=1)
        if self.gestor.en_descanso():
            self.intervalos_en_descanso += 1
            if self.intervalos_en_descanso % INTERVALOS_DE_DESCANSO == 0:
                self.gestor.terminar(completado=True)
        if resumen.tiempo >= DURACION_S:
            self.sesion.detener()

    def al_detectar_fatiga(self, resumen):
        self.alertas.append(resumen.tiempo)
        if self.gestor.en_descanso():
            self.alertas_en_descanso += 1
        if self.gestor.recibir_alerta():
            self.alertas_mostradas += 1
            self.gestor.aceptar_alerta(minutos=1)


class AhoraFalso:
    def __init__(self):
        self.momento = datetime(2026, 11, 6, 10, 0, 0)

    def __call__(self):
        return self.momento


def test_flujo_completo_con_la_simulacion(original, tmp_path):
    constantes = original.constantes
    ahora = AhoraFalso()
    gestor = GestorDescansos(tmp_path, ahora=ahora)
    oyente = OyenteFlujo(gestor, ahora)

    def abrir_dispositivo(detener, avisar):
        return DispositivoSimulado(
            "fatigue_test", original.fs, constantes["SIM_BASELINE_DURATION_S"], velocidad=None
        )

    sesion = SesionMedicion(
        original, parametros_del_original(constantes, sim=True), abrir_dispositivo, tmp_path, "prueba", oyente
    )
    oyente.sesion = sesion
    gestor.conectar_medicion(sesion)
    sesion.ejecutar()

    # Hubo varias alertas, cada una después de terminar el descanso anterior.
    assert len(oyente.alertas) >= 2
    assert oyente.alertas_mostradas == len(oyente.alertas)
    assert oyente.alertas_en_descanso == 0
    assert all(d["origen"] == ORIGEN_FATIGA and d["completado"] for d in gestor.historial)
    assert len(gestor.historial) >= 1

    # La línea base se tomó una sola vez, al comienzo.
    assert len(sesion.regla.linea_base_rms) == sesion.regla.puntos_linea_base
