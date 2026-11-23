"""
Actividad, índice de fatiga, tendencias y alerta: réplica de la celda 7 ("Adquisición
sEMG") y del cuerpo del ciclo de la celda 11 del notebook 4.2, sin cambiar los cálculos.

El notebook guarda todo en variables globales; aquí viven en un AnalizadorFatiga (uno
por grabación):
- robust_sd(), umbral_actividad()      <- celda 7, iguales
- detectar_actividad(), calcular_fatiga(), prueba_pendientes(), cerrar_intervalo()
                                       <- celda 7, mismos cálculos
- procesar_bloque()                    <- celda 11, cuerpo del while (desde evaluar_calidad)

Cambio pedido para la app: el notebook alerta una sola vez por grabación. Aquí, cuando
el usuario cierra el pop-up, la alerta vuelve a estar disponible pasados
rearme_alerta_s segundos de señal (con rearme_alerta_s=None se comporta como el notebook).
También se puede cambiar el umbral de alerta durante la grabación.

Qué se puede editar aquí: los textos de los motivos. Los parámetros están en configuracion.py.
"""

import math
import statistics
from dataclasses import dataclass, field

from scipy.stats import linregress

from configuracion import (
    BASELINE_ACTIVE_S,
    FS,
    MDF_DECREASE_THRESHOLD,
    RMS_ACTIVE_K,
    RMS_ACTIVE_MIN_RATIO,
    RMS_FALLBACK_INIT_S,
    RMS_INCREASE_THRESHOLD,
    SETTLING_S,
    SLOPE_MIN_POINTS,
    SLOPE_MIN_SPAN_FRACTION,
    SLOPE_P_THRESHOLD,
    SLOPE_WINDOW_S,
    TREND_INTERVAL_S,
    USE_SLOPE_TEST,
)
from procesamiento import evaluar_calidad, texto_calidad

ENCABEZADO_TENDENCIAS = [
    "Time (s)", "Mean RMS (ADC)", "Median MDF (Hz)", "Fatigue index (%)",
    "Active seconds", "Partial interval",
]
ENCABEZADO_CRUDO = ["Time (s)", "EMG raw (ADC)", "Settling", "Quality flag"]
ENCABEZADO_BLOQUES = [
    "Time (s)", "RMS (ADC)", "MDF (Hz)", "Settling", "Active",
    "Fatigue index (%)",
]
COLUMNA_MVC = "RMS (%MVC)"
COLUMNA_CALIDAD = "Quality flag"
MAXIMO_HISTORIAL_REPOSO_MOVIL = 60  # celda 7: fallback_rms_history[-60:]


def robust_sd(valores):
    if not valores:
        return float("nan")
    mediana = statistics.median(valores)
    return 1.4826 * statistics.median(
        [abs(valor - mediana) for valor in valores]
    )


def umbral_actividad(mediana, sd):
    """Umbral Active = max(mediana + K·SD, RATIO × mediana)."""
    return max(mediana + RMS_ACTIVE_K * sd, RMS_ACTIVE_MIN_RATIO * mediana)


def encabezados(mvc_rms):
    """Encabezados de los CSV de tendencias y de bloques (celda 11)."""
    tendencias = list(ENCABEZADO_TENDENCIAS)
    bloques = list(ENCABEZADO_BLOQUES)
    if mvc_rms is not None:
        tendencias.append(COLUMNA_MVC)
        bloques.append(COLUMNA_MVC)
    tendencias.append(COLUMNA_CALIDAD)
    bloques.append(COLUMNA_CALIDAD)
    return tendencias, bloques


@dataclass
class ResumenIntervalo:
    """Una fila del CSV de tendencias, más lo que necesita la ventana."""

    fila: list
    tiempo: float
    rms: float
    mdf: float
    fatiga: float
    parcial: bool
    calidad: str
    alerta: bool  # True si este intervalo disparó la alerta
    mensajes: list = field(default_factory=list)  # lo que el notebook imprime


@dataclass
class ResultadoBloque:
    fila: list  # fila del CSV por bloque
    tiempo: float
    rms: float
    mdf: float
    fatiga: float
    activo: bool
    asentamiento: bool
    calidad: str
    resumen: ResumenIntervalo = None  # intervalo que se cerró con este bloque (o None)


class AnalizadorFatiga:
    def __init__(self, reposo, umbral_alerta, mvc_rms=None, rearme_alerta_s=None):
        """
        reposo: ResultadoReposo de la calibración (o None si no se calibró).
        umbral_alerta: FATIGUE_ALERT_THRESHOLD ("Porcentaje de alerta").
        """
        if not 0 <= umbral_alerta <= 100:
            raise ValueError("El porcentaje de alerta debe estar entre 0 y 100.")
        if mvc_rms is not None and mvc_rms <= 0:
            raise ValueError("MVC_RMS debe ser mayor que cero.")
        # Celda 7: estado inicial
        self.rest_rms_median = reposo.rms_mediana if reposo else None
        self.rest_rms_robust_sd = reposo.rms_sd_robusta if reposo else None
        self.rest_check_passed = bool(reposo and reposo.paso)
        self.umbral_alerta = umbral_alerta
        self.mvc_rms = mvc_rms
        self.rearme_alerta_s = rearme_alerta_s

        self.baseline_rms = []
        self.baseline_mdf = []
        self.baseline_active_elapsed = 0.0
        self.rms_baseline_level = None
        self.mdf_baseline_level = None
        self.alerta_fatiga_activada = False
        self.fallback_rms_history = []
        self.slope_history = []
        self.ultimo_active = False
        self.ultimo_quality_flag = "PENDIENTE"
        self.ultimo_fatigue_reason = "La comprobación de reposo no se ha ejecutado."
        self.ultimo_mensaje_supresion = None

        self.bin_tiempos, self.bin_rms, self.bin_mdf, self.bin_fatiga = [], [], [], []
        self.bin_active, self.bin_active_rms, self.bin_active_mdf = [], [], []
        self.bin_duraciones, self.bin_quality, self.bin_rms_mvc = [], [], []
        self.intervalo_actual = None
        self.ultima_fatiga_intervalo = float("nan")

        # Nuevo en la app: rearme de la alerta
        self.pedido_cierre_alerta = False
        self.rearme_en = None

    # --- Celda 7 ---

    def detectar_actividad(self, rms, asentamiento):
        if asentamiento:
            return False, "periodo de asentamiento"
        if self.rest_rms_median is not None and self.rest_rms_robust_sd is not None:
            umbral = umbral_actividad(self.rest_rms_median, self.rest_rms_robust_sd)
            return rms > umbral, f"umbral de reposo {umbral:.3f}"

        muestras_iniciales = max(1, math.ceil(RMS_FALLBACK_INIT_S))
        if len(self.fallback_rms_history) < muestras_iniciales:
            self.fallback_rms_history.append(rms)
            return False, (
                f"estimación móvil sin calibración; reuniendo "
                f"{len(self.fallback_rms_history)}/{muestras_iniciales} bloques"
            )
        umbral = umbral_actividad(
            statistics.median(self.fallback_rms_history), robust_sd(self.fallback_rms_history)
        )
        activo = rms > umbral
        if not activo:
            self.fallback_rms_history.append(rms)
            self.fallback_rms_history = self.fallback_rms_history[-MAXIMO_HISTORIAL_REPOSO_MOVIL:]
        return activo, f"estimación móvil sin calibración; umbral {umbral:.3f}"

    def calcular_fatiga(self, rms, mdf, activo, asentamiento, duracion_bloque):
        """Índice = 100 × promedio de [clip(RMS/RMS_base − 1, 0, 1), clip(1 − MDF/MDF_base, 0, 1)].
        La base son los primeros BASELINE_ACTIVE_S segundos activos no asentados. NaN si no
        hay comprobación de reposo PASS, el bloque no está activo o falta la base."""
        if asentamiento or not activo or not self.rest_check_passed:
            return float("nan")
        if not (math.isfinite(rms) and math.isfinite(mdf)) or rms <= 0 or mdf <= 0:
            return float("nan")
        if self.rms_baseline_level is None or self.mdf_baseline_level is None:
            tiempo_restante = BASELINE_ACTIVE_S - self.baseline_active_elapsed
            if tiempo_restante > 0:
                self.baseline_rms.append(rms)
                self.baseline_mdf.append(mdf)
                self.baseline_active_elapsed += min(duracion_bloque, tiempo_restante)
            if self.baseline_active_elapsed < BASELINE_ACTIVE_S:
                return float("nan")
            self.rms_baseline_level = statistics.median(self.baseline_rms)
            self.mdf_baseline_level = statistics.median(self.baseline_mdf)
            return 0.0
        aumento_rms = min(1.0, max(0.0, rms / self.rms_baseline_level - 1.0))
        descenso_mdf = min(1.0, max(0.0, 1.0 - mdf / self.mdf_baseline_level))
        return 100.0 * (aumento_rms + descenso_mdf) / 2.0

    def prueba_pendientes(self, tiempo_actual):
        """Regresión de RMS y MDF sobre los bloques Active de los últimos SLOPE_WINDOW_S."""
        if not USE_SLOPE_TEST:
            return True
        tolerancia = 1e-6
        # Nuevo en la app: se olvidan los puntos que ya quedaron fuera de la ventana, para
        # que una grabación de 24 h no acumule memoria. No cambia el resultado, porque el
        # tiempo solo avanza y esos puntos no se vuelven a usar.
        desde = tiempo_actual - SLOPE_WINDOW_S - tolerancia
        while self.slope_history and self.slope_history[0][0] < desde:
            self.slope_history.pop(0)
        puntos = [
            punto for punto in self.slope_history
            if tiempo_actual - SLOPE_WINDOW_S - tolerancia <= punto[0] <= tiempo_actual + tolerancia
        ]
        if len(puntos) < SLOPE_MIN_POINTS:
            return False
        if puntos[-1][0] - puntos[0][0] < SLOPE_MIN_SPAN_FRACTION * SLOPE_WINDOW_S:
            return False
        tiempos = [punto[0] for punto in puntos]
        ajuste_rms = linregress(tiempos, [punto[1] for punto in puntos])
        ajuste_mdf = linregress(tiempos, [punto[2] for punto in puntos])
        return (
            ajuste_rms.slope > 0 and ajuste_rms.pvalue < SLOPE_P_THRESHOLD
            and ajuste_mdf.slope < 0 and ajuste_mdf.pvalue < SLOPE_P_THRESHOLD
        )

    def cerrar_intervalo(self, parcial=False):
        """Resume el intervalo actual (fila del CSV de tendencias) y revisa la alerta."""
        if not self.bin_tiempos:
            return None
        mensajes = []
        duracion_intervalo = sum(self.bin_duraciones)
        parcial = parcial or duracion_intervalo < TREND_INTERVAL_S - 1e-6
        rms_resumen = statistics.mean(self.bin_rms) if self.bin_rms else float("nan")
        mdf_resumen = statistics.median(self.bin_mdf) if self.bin_mdf else float("nan")
        fatiga_resumen = statistics.median(self.bin_fatiga) if self.bin_fatiga else float("nan")
        segundos_activos = sum(
            duracion for activo, duracion in zip(self.bin_active, self.bin_duraciones)
            if activo
        )
        tiempo_tendencia = self.intervalo_actual * TREND_INTERVAL_S + min(
            TREND_INTERVAL_S, duracion_intervalo
        ) / 2
        marcas = sorted({marca for marca in self.bin_quality if marca != "OK"})
        calidad_resumen = ";".join(marcas) if marcas else "OK"

        if not self.rest_check_passed:
            self.ultimo_fatigue_reason = "índice suprimido: la comprobación de reposo no fue PASS"
        elif not self.bin_active_rms:
            self.ultimo_fatigue_reason = "índice suprimido: no hubo bloques Active"
        elif self.rms_baseline_level is None:
            self.ultimo_fatigue_reason = "índice suprimido: línea base Active aún incompleta"
        else:
            self.ultimo_fatigue_reason = "índice disponible solo para bloques Active"

        alerta = False
        if (
            not self.alerta_fatiga_activada
            and math.isfinite(fatiga_resumen)
            and fatiga_resumen >= self.umbral_alerta
            and self.bin_active_rms and self.bin_active_mdf
            and self.rms_baseline_level is not None and self.mdf_baseline_level is not None
        ):
            rms_activo = statistics.median(self.bin_active_rms)
            mdf_activo = statistics.median(self.bin_active_mdf)
            umbrales_cumplidos = (
                rms_activo >= self.rms_baseline_level * (1 + RMS_INCREASE_THRESHOLD)
                and mdf_activo <= self.mdf_baseline_level * (1 - MDF_DECREASE_THRESHOLD)
            )
            pendientes_ok = self.prueba_pendientes(self.bin_tiempos[-1])
            if umbrales_cumplidos and pendientes_ok:
                self.alerta_fatiga_activada = True
                alerta = True
                mensajes.append(
                    f"ALERTA de tendencia compatible con fatiga: índice "
                    f"{fatiga_resumen:.1f}%. Resultado no validado."
                )

        fila = [
            tiempo_tendencia, rms_resumen, mdf_resumen, fatiga_resumen,
            segundos_activos, parcial,
        ]
        if self.mvc_rms is not None:
            fila.append(100 * rms_resumen / self.mvc_rms if math.isfinite(rms_resumen) else float("nan"))
        fila.append(calidad_resumen)
        if not math.isfinite(fatiga_resumen):
            if self.ultimo_fatigue_reason != self.ultimo_mensaje_supresion:  # solo cuando cambia el motivo
                mensajes.append(f"Fatigue index (%) suprimido: {self.ultimo_fatigue_reason}.")
                self.ultimo_mensaje_supresion = self.ultimo_fatigue_reason
        if parcial:
            mensajes.append(f"Intervalo final parcial ({duracion_intervalo:.2f} s); marcado como parcial.")
        for lista in (
            self.bin_tiempos, self.bin_rms, self.bin_mdf, self.bin_fatiga, self.bin_active,
            self.bin_active_rms, self.bin_active_mdf, self.bin_duraciones, self.bin_quality,
            self.bin_rms_mvc,
        ):
            lista.clear()
        self.ultima_fatiga_intervalo = fatiga_resumen
        return ResumenIntervalo(
            fila, tiempo_tendencia, rms_resumen, mdf_resumen, fatiga_resumen, parcial,
            calidad_resumen, alerta, mensajes,
        )

    # --- Celda 11: cuerpo del ciclo de adquisición ---

    def procesar_bloque(self, indice_inicio_bloque, mediciones_bloque, rms, mdf):
        """
        indice_inicio_bloque: n_medicion antes de leer el bloque.
        mediciones_bloque: [(tiempo, valor), ...] del bloque.
        rms, mdf: los que devolvió ProcesadorEMG.procesar_bloque().
        """
        valores_crudos = [valor for _, valor in mediciones_bloque]
        calidad = evaluar_calidad(valores_crudos, FS)
        bandera_calidad = texto_calidad(calidad, self.rest_check_passed)
        asentamiento = indice_inicio_bloque / FS < SETTLING_S
        activo, motivo_actividad = self.detectar_actividad(rms, asentamiento)
        tiempo_bloque = statistics.mean(tiempo for tiempo, _ in mediciones_bloque)
        duracion_bloque = len(mediciones_bloque) / FS
        fatiga = self.calcular_fatiga(rms, mdf, activo, asentamiento, duracion_bloque)
        if activo and not asentamiento and math.isfinite(mdf):
            self.slope_history.append((tiempo_bloque, rms, mdf))
        self.ultimo_active = activo
        self.ultimo_quality_flag = bandera_calidad
        if not self.rest_check_passed:
            self.ultimo_fatigue_reason = "índice suprimido: la comprobación de reposo no fue PASS"
        elif not activo:
            self.ultimo_fatigue_reason = f"índice suprimido: bloque no Active ({motivo_actividad})"
        elif not math.isfinite(fatiga):
            self.ultimo_fatigue_reason = "índice suprimido: línea base Active aún incompleta"
        else:
            self.ultimo_fatigue_reason = "índice calculado para bloque Active"
        mvc_pct = (
            100 * rms / self.mvc_rms
            if self.mvc_rms is not None and self.mvc_rms > 0 else float("nan")
        )
        fila_bloque = [tiempo_bloque, rms, mdf, asentamiento, activo, fatiga]
        if self.mvc_rms is not None:
            fila_bloque.append(mvc_pct)
        fila_bloque.append(bandera_calidad)

        self.revisar_rearme(tiempo_bloque)
        resumen = None
        intervalo = int((indice_inicio_bloque / FS) // TREND_INTERVAL_S)
        if self.intervalo_actual is not None and intervalo != self.intervalo_actual:
            resumen = self.cerrar_intervalo()
        self.intervalo_actual = intervalo
        self.bin_tiempos.append(tiempo_bloque)
        self.bin_duraciones.append(duracion_bloque)
        self.bin_active.append(activo and not asentamiento)
        self.bin_quality.append(bandera_calidad)
        if not asentamiento and math.isfinite(rms):
            self.bin_rms.append(rms)
            if self.mvc_rms is not None:
                self.bin_rms_mvc.append(mvc_pct)
        if activo and not asentamiento:
            if math.isfinite(mdf):
                self.bin_mdf.append(mdf)
                self.bin_active_mdf.append(mdf)
            self.bin_active_rms.append(rms)
            if math.isfinite(fatiga):
                self.bin_fatiga.append(fatiga)

        return ResultadoBloque(
            fila_bloque, tiempo_bloque, rms, mdf, fatiga, activo, asentamiento, bandera_calidad, resumen
        )

    # --- Nuevo en la app: rearme de la alerta ---

    def cerrar_alerta(self):
        """El usuario cerró el pop-up. Puede llamarse desde otro hilo: se aplica en el bloque siguiente."""
        self.pedido_cierre_alerta = True

    def revisar_rearme(self, tiempo):
        if self.pedido_cierre_alerta:
            self.pedido_cierre_alerta = False
            if self.alerta_fatiga_activada and self.rearme_alerta_s is not None:
                self.rearme_en = tiempo + self.rearme_alerta_s
        if self.rearme_en is not None and tiempo >= self.rearme_en:
            self.alerta_fatiga_activada = False
            self.rearme_en = None
