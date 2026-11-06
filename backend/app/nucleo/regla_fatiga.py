"""
Regla de fatiga: agrupa los bloques en intervalos de tendencia, calcula la línea
base y decide cuándo hay un patrón de fatiga sostenido.

Es una réplica fiel de la celda "Adquisición de sEMG" de Código_Bitalino_Python.py:
- __init__()          <- líneas 177-183 y 231-233 (puntos necesarios y variables de estado)
- agregar_bloque()    <- líneas 427-440 (asignar cada bloque a su intervalo)
- cerrar_intervalo()  <- función cerrar_intervalo(), líneas 236-294, sin el gráfico ni el CSV
La matemática no cambia. Lo único nuevo, pedido para la app:
- rearmar(): después de un descanso la alerta vuelve a estar disponible
  (el original alerta una sola vez por sesión). La línea base se mantiene.
- pausada: durante un descanso no se evalúa el patrón ni se toma línea base.

Qué se puede editar aquí: los textos de los mensajes. Los umbrales y tiempos se
cambian en el original o en los ajustes de la app.
"""

import math
import statistics
from dataclasses import dataclass

# Mensaje de alerta del original (líneas 278-283), tal cual.
MENSAJE_ALERTA_ORIGINAL = (
    "POTENTIAL FATIGUE TREND: RMS is consistently elevated "
    "and MDF is consistently reduced. Pause the task and "
    "assess how the muscle feels. This signal is not a "
    "medical diagnosis."
)

# Mensaje de alerta de la celda de simulación del original (líneas 580-582), tal cual.
MENSAJE_ALERTA_SIMULADA = (
    "SIMULATED ALERT: the test signal sustained the configured "
    "RMS/MDF pattern. This is only a software test, not a "
    "medical or physiological conclusion."
)

# Aclaración del original ("This signal is not a medical diagnosis") traducida para la interfaz.
ACLARACION_MEDICA = "Esta señal no es un diagnóstico médico."


@dataclass
class ResumenIntervalo:
    tiempo: float  # Time (s)
    rms: float  # Mean RMS (ADC)
    mdf: float  # Median MDF (Hz)
    alerta: bool  # True si este intervalo disparó la alerta de fatiga


class ReglaFatiga:
    def __init__(self, intervalo_s, linea_base_s, persistencia_s, umbral_rms, umbral_mdf):
        self.intervalo_s = intervalo_s
        self.umbral_rms = umbral_rms
        self.umbral_mdf = umbral_mdf

        # Líneas 177-178
        self.puntos_linea_base = math.ceil(linea_base_s / intervalo_s)  # baseline_points_needed
        self.puntos_persistencia = math.ceil(persistencia_s / intervalo_s)  # persistence_points_needed

        # Líneas 180-183
        self.linea_base_rms = []  # baseline_rms
        self.linea_base_mdf = []  # baseline_mdf
        self.racha = 0  # fatigue_pattern_streak
        self.alertada = False  # fatigue_alerted

        # Líneas 231-233 y 323: valores del intervalo de tendencia actual
        self.bin_tiempos = []
        self.bin_rms = []
        self.bin_mdf = []
        self.intervalo_actual = None

        # Nuevo en la app: True durante un descanso
        self.pausada = False

    @classmethod
    def desde_parametros(cls, parametros):
        """Crea la regla con un diccionario que usa los nombres del original."""
        return cls(
            intervalo_s=parametros["TREND_INTERVAL_S"],
            linea_base_s=parametros["BASELINE_DURATION_S"],
            persistencia_s=parametros["ALERT_PERSISTENCE_S"],
            umbral_rms=parametros["RMS_INCREASE_THRESHOLD"],
            umbral_mdf=parametros["MDF_DECREASE_THRESHOLD"],
        )

    def calibrando(self):
        """True mientras se juntan los puntos de la línea base."""
        return len(self.linea_base_rms) < self.puntos_linea_base

    def linea_base(self):
        """(RMS base, MDF base) con la mediana, como en las líneas 261-262; None si falta."""
        if self.calibrando():
            return None
        return statistics.median(self.linea_base_rms), statistics.median(self.linea_base_mdf)

    def agregar_bloque(self, tiempo_bloque, rms, mdf):
        """
        Agrega el RMS y la MDF de un bloque (líneas 428-440).
        Si el bloque empieza un intervalo nuevo, cierra el anterior y devuelve su resumen.
        """
        resumen = None
        intervalo = int(tiempo_bloque // self.intervalo_s)

        if self.intervalo_actual is not None and intervalo != self.intervalo_actual:
            resumen = self.cerrar_intervalo()

        self.intervalo_actual = intervalo
        self.bin_tiempos.append(tiempo_bloque)
        self.bin_rms.append(rms)
        self.bin_mdf.append(mdf)
        return resumen

    def cerrar_intervalo(self):
        """Resume el intervalo actual y evalúa el patrón de fatiga (líneas 239-283)."""
        if not self.bin_tiempos:
            return None

        # Líneas 243-252
        tiempo_tendencia = statistics.mean(self.bin_tiempos)
        rms_resumen = statistics.mean(self.bin_rms)
        mdf_validos = [valor for valor in self.bin_mdf if math.isfinite(valor)]
        mdf_resumen = statistics.median(mdf_validos) if mdf_validos else float("nan")

        alerta = False
        # Líneas 255-277 (más la condición nueva "not self.pausada")
        if math.isfinite(rms_resumen) and math.isfinite(mdf_resumen) and not self.pausada:
            if len(self.linea_base_rms) < self.puntos_linea_base:
                self.linea_base_rms.append(rms_resumen)
                self.linea_base_mdf.append(mdf_resumen)

            elif not self.alertada:
                rms_base = statistics.median(self.linea_base_rms)
                mdf_base = statistics.median(self.linea_base_mdf)

                patron_fatiga = (
                    rms_resumen >= rms_base * (1 + self.umbral_rms)
                    and mdf_resumen <= mdf_base * (1 - self.umbral_mdf)
                )

                if patron_fatiga:
                    self.racha += 1
                else:
                    self.racha = 0

                if self.racha >= self.puntos_persistencia:
                    self.alertada = True
                    alerta = True

        # Líneas 316-318
        self.bin_tiempos.clear()
        self.bin_rms.clear()
        self.bin_mdf.clear()

        return ResumenIntervalo(tiempo_tendencia, rms_resumen, mdf_resumen, alerta)

    def rearmar(self):
        """Vuelve a permitir la alerta (después de un descanso). La línea base se mantiene."""
        self.alertada = False
        self.racha = 0
