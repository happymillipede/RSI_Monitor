"""
Funciones de ayuda para las pruebas.

- parametros_del_original(): parámetros de detección del original (normales o SIM_*).
- simular(): corre una sesión de medición simulada, sin esperar tiempo real.
- archivo_descansos(): datos/descansos.json dentro de una carpeta de prueba.
"""

import json

from app.nucleo.adquisicion import Oyente, SesionMedicion
from app.almacenamiento import PARAMETROS_DETECCION, RUTA_CONFIG_EJEMPLO, ArchivoDescansos
from app.nucleo.simulador import DispositivoSimulado


def parametros_del_original(constantes, sim=False):
    """Parámetros de detección tal como están en el original (normales o SIM_*)."""
    return {
        nombre: constantes["SIM_" + nombre] if sim else constantes[nombre]
        for nombre in PARAMETROS_DETECCION
    }


class OyenteRegistro(Oyente):
    """Guarda todo lo que avisa la sesión y la detiene después de 'duracion_s' de señal."""

    def __init__(self, duracion_s, periodo):
        self.duracion_s = duracion_s
        self.periodo = periodo
        self.sesion = None
        self.estados = []
        self.bloques = []
        self.resumenes = []
        self.alertas = []

    def al_cambiar_estado(self, estado, detalle=""):
        self.estados.append(estado)

    def al_procesar_bloque(self, info):
        self.bloques.append(info)
        if info.n_medicion * self.periodo >= self.duracion_s:
            self.sesion.detener()

    def al_cerrar_intervalo(self, resumen, linea_base):
        self.resumenes.append(resumen)

    def al_detectar_fatiga(self, resumen):
        self.alertas.append(resumen)


def simular(original, carpeta, escenario, duracion_s, sim=False, parametros=None):
    """Corre una sesión simulada y devuelve (sesion, oyente)."""
    constantes = original.constantes
    parametros = parametros or parametros_del_original(constantes, sim)
    oyente = OyenteRegistro(duracion_s, constantes["PERIODO"])

    def abrir_dispositivo(detener, avisar):
        return DispositivoSimulado(
            escenario, original.fs, constantes["SIM_BASELINE_DURATION_S"], velocidad=None
        )

    sesion = SesionMedicion(original, parametros, abrir_dispositivo, carpeta, "prueba", oyente)
    oyente.sesion = sesion
    sesion.ejecutar()
    return sesion, oyente


def archivo_descansos(carpeta):
    """ArchivoDescansos en 'carpeta', con las plantillas iniciales de config.ejemplo.json."""
    ejemplo = json.loads(RUTA_CONFIG_EJEMPLO.read_text(encoding="utf-8"))
    return ArchivoDescansos(carpeta, ejemplo["descansos"]["plantillas_iniciales"])
