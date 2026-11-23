"""
Calibraciones antes de grabar, copiadas del notebook 4.2 sin cambiar los cálculos:

- comprobar_reposo()  <- celda 9 "Comprobación de reposo antes de la sesión" (botón Calibrar)
- calibrar_mvc()      <- celda 10 "Calibración opcional de MVC" (pestaña Detalles)

El notebook imprime los resultados con print(); aquí se juntan en una lista de líneas
que la ventana muestra en la pestaña Detalles. Además, las dos se pueden cortar con el
evento "detener" (la app se cierra o el usuario cancela).

Qué se puede editar aquí: los textos. Los parámetros están en configuracion.py.
"""

import statistics
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.signal import welch

from configuracion import (
    CANAL,
    FS,
    HUM_RESIDUAL_BAND_HZ,
    MAINS_AMPLITUDE_LIMIT_COUNTS,
    MAINS_NOTCH_HZ,
    MVC_COUNTDOWN_S,
    MVC_REST_S,
    MVC_S,
    MVC_TRIALS,
    N,
    QUALITY_LINE_HALF_BAND_HZ,
    REST_CHECK_S,
    REST_MAX_MIN_RATIO,
    SETTLING_S,
)
from fatiga import robust_sd, umbral_actividad
from procesamiento import ProcesadorEMG, dispositivo_es_simulado, evaluar_calidad


@dataclass
class ResultadoReposo:
    paso: bool  # rest_check_passed
    rms_mediana: float  # rest_rms_median
    rms_sd_robusta: float  # rest_rms_robust_sd
    motivos: list = field(default_factory=list)  # por qué no pasó (vacío si PASS)
    lineas: list = field(default_factory=list)  # lo que imprime el notebook

    @property
    def texto_estado(self):
        return "PASS" if self.paso else "WARN"


def no_avisar(texto):
    pass


def leer_muestras(dispositivo, cantidad_total, detener=None, avisar_progreso=None):
    """Lee cantidad_total muestras en bloques de N (start/stop como el notebook)."""
    datos = []
    dispositivo.start(FS, [CANAL])
    try:
        restantes = cantidad_total
        while restantes:
            if detener is not None and detener.is_set():
                raise InterruptedError("Calibración cancelada.")
            cantidad = min(N, restantes)
            tramas = dispositivo.read(cantidad)
            datos.extend(int(trama[5]) for trama in tramas)
            restantes -= len(tramas)
            if avisar_progreso:
                avisar_progreso(len(datos) / cantidad_total)
    finally:
        dispositivo.stop()
    return datos


def comprobar_reposo(dispositivo, detener=None, avisar_progreso=None):
    """Celda 9: mide REST_CHECK_S de reposo y decide si la calibración pasa (PASS) o no (WARN)."""
    lineas = []
    cantidad_total = round(REST_CHECK_S * FS)
    simulado = dispositivo_es_simulado(dispositivo)
    lineas.append(f"Dispositivo: {'SIMULADO' if simulado else 'BITalino real'}")
    lineas.append(f"Mantén el músculo en reposo durante {REST_CHECK_S:g} s...")
    datos_crudos = leer_muestras(dispositivo, cantidad_total, detener, avisar_progreso)

    procesador_reposo = ProcesadorEMG(FS)
    rms_reposo, mdf_reposo, filtrada_reposo = [], [], []
    muestras_por_bloque = max(32, round(FS))
    for inicio in range(0, len(datos_crudos), muestras_por_bloque):
        bloque = datos_crudos[inicio:inicio + muestras_por_bloque]
        if len(bloque) < 32:
            continue
        muestras = [(i / FS, valor) for i, valor in enumerate(bloque)]
        rms, mdf = procesador_reposo.procesar_bloque(muestras)
        if inicio / FS >= SETTLING_S:
            rms_reposo.append(rms)
            mdf_reposo.append(mdf)
            filtrada_reposo.extend(procesador_reposo.ultima_filtrada.tolist())
    calidad = evaluar_calidad(datos_crudos, FS)
    rest_rms_median = statistics.median(rms_reposo) if rms_reposo else None
    rest_rms_robust_sd = robust_sd(rms_reposo) if rms_reposo else None
    lineas_dentro_limite = all(
        calidad["line_rms"][hz] <= MAINS_AMPLITUDE_LIMIT_COUNTS
        for hz in MAINS_NOTCH_HZ
    )
    # ¿Era realmente reposo? Los bloques de reposo no deben variar mucho entre sí.
    if rms_reposo and min(rms_reposo) > 0:
        razon_max_min = max(rms_reposo) / min(rms_reposo)
    else:
        razon_max_min = float("inf")
    reposo_estable = bool(rms_reposo) and razon_max_min <= REST_MAX_MIN_RATIO
    rest_check_passed = (
        calidad["clipped_count"] == 0
        and lineas_dentro_limite
        and rest_rms_median is not None
        and reposo_estable
    )

    # Ruido de red residual tras el filtrado (informativo; no condiciona el PASS).
    fraccion_red = float("nan")
    if len(filtrada_reposo) >= 32:
        nperseg = min(len(filtrada_reposo), round(FS))
        frecuencias, potencia = welch(
            np.asarray(filtrada_reposo), fs=FS, nperseg=nperseg,
            noverlap=nperseg // 2, detrend="constant", scaling="density",
        )
        en_banda = (frecuencias >= 25) & (frecuencias <= 400)
        cerca_red = np.zeros_like(en_banda)
        for hz in MAINS_NOTCH_HZ:
            cerca_red |= np.abs(frecuencias - hz) <= HUM_RESIDUAL_BAND_HZ
        total = float(np.sum(potencia[en_banda]))
        if total > 0:
            fraccion_red = float(np.sum(potencia[en_banda & cerca_red]) / total)

    lineas.append(f"Reposo previo: {REST_CHECK_S:g} s")
    lineas.append(f"Clipped: {calidad['clipped_count']} ({calidad['clipped_percent']:.4f}%)")
    for hz in MAINS_NOTCH_HZ:
        lineas.append(
            f"Línea cruda {hz:.0f} Hz RMS (±{QUALITY_LINE_HALF_BAND_HZ:g} Hz): "
            f"{calidad['line_rms'][hz]:.2f} counts (límite {MAINS_AMPLITUDE_LIMIT_COUNTS:g})"
        )
    for hz, razon in calidad["peak_ratio"].items():
        lineas.append(f"Welch peak/local floor {hz:.0f} Hz: {razon:.2f}")
    lineas.append(f"RMS filtrado de reposo (mediana): {rest_rms_median}")
    lineas.append(f"RMS filtrado robust SD (1.4826×MAD): {rest_rms_robust_sd}")
    lineas.append(f"Bloques de reposo máx/mín: {razon_max_min:.2f} (límite {REST_MAX_MIN_RATIO:g})")
    lineas.append(
        f"MDF filtrada de reposo (mediana): {statistics.median(mdf_reposo) if mdf_reposo else float('nan')}"
        " (sin significado fisiológico en reposo)"
    )
    lineas.append(f"Potencia filtrada de reposo cerca de armónicas de red: {fraccion_red:.1%} (informativo)")
    motivos = []
    if rest_check_passed:
        lineas.append("PASS")
    else:
        if calidad["clipped_count"]:
            motivos.append("hay muestras clipped")
        if not lineas_dentro_limite:
            motivos.append("alguna línea de red supera el límite provisional")
        if not reposo_estable:
            motivos.append("el reposo no es estable (¿se movió o contrajo el músculo?)")
        lineas.append("WARN: " + "; ".join(motivos) + ". El índice de fatiga quedará suprimido.")
    if simulado:
        lineas.append("AVISO: dispositivo simulado; este resultado no valida el hardware ni la colocación de electrodos.")
    if rest_rms_median is None:
        raise RuntimeError("No se pudieron obtener bloques válidos para calibrar el reposo.")
    return ResultadoReposo(rest_check_passed, rest_rms_median, rest_rms_robust_sd, motivos, lineas)


def calibrar_mvc(dispositivo, reposo=None, detener=None, avisar=no_avisar, dormir=None):
    """
    Celda 10: MVC_RMS = mayor RMS de 1 s entre MVC_TRIALS contracciones máximas. Se
    descartan los primeros SETTLING_S de cada ensayo. Devuelve MVC_RMS.
    dormir(segundos): espera interrumpible (por defecto, detener.wait o time.sleep).
    """
    if dormir is None:
        dormir = detener.wait if detener is not None else time.sleep

    def esperar(segundos):
        dormir(segundos)
        if detener is not None and detener.is_set():
            raise InterruptedError("Calibración de MVC cancelada.")

    mejores = []
    for ensayo in range(1, MVC_TRIALS + 1):
        for segundo in range(int(MVC_COUNTDOWN_S), 0, -1):
            avisar(f"Ensayo {ensayo}/{MVC_TRIALS}: contracción máxima en {segundo}...")
            esperar(1)
        avisar(f"¡CONTRAE AL MÁXIMO durante {MVC_S:g} s!")
        total = round(MVC_S * FS)
        datos = leer_muestras(dispositivo, total, detener)
        procesador_mvc = ProcesadorEMG(FS)
        valores_rms = []
        tamano_bloque = max(32, round(FS))
        for inicio in range(0, len(datos), tamano_bloque):
            bloque = datos[inicio:inicio + tamano_bloque]
            if len(bloque) < 32:
                continue
            muestras = [(i / FS, valor) for i, valor in enumerate(bloque)]
            rms, _ = procesador_mvc.procesar_bloque(muestras)
            if inicio / FS >= SETTLING_S:
                valores_rms.append(rms)
        if not valores_rms:
            raise RuntimeError("No hubo bloques válidos para calcular MVC_RMS (aumenta MVC_S).")
        mejores.append(max(valores_rms))
        avisar(f"  Ensayo {ensayo}: mejor RMS de 1 s = {mejores[-1]:.3f} ADC.")
        if ensayo < MVC_TRIALS:
            avisar(f"Descansa {MVC_REST_S:g} s...")
            esperar(MVC_REST_S)
    mvc_rms = max(mejores)
    avisar(f"MVC_RMS calibrado: {mvc_rms:.3f} ADC (máximo de {len(mejores)} ensayos).")
    if reposo is not None and mvc_rms <= umbral_actividad(reposo.rms_mediana, reposo.rms_sd_robusta):
        avisar("AVISO: MVC_RMS no supera el umbral Active; repite la calibración con más esfuerzo o revisa los electrodos.")
    return mvc_rms
