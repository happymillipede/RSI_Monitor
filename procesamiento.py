"""
Procesamiento de la señal sEMG y simulador, copiados del notebook 4.2
(originales/bitalino_codigo (Ver 4.2).ipynb) sin cambiar los cálculos.

- BITalinoSimulado    <- celda 3 "Simulador EMG"
- ProcesadorEMG       <- celda 6 "Procesador sEMG": notches de red en cascada,
                         pasabanda 25-400 Hz, RMS y MDF (Welch)
- evaluar_calidad()   <- celda 6: clipping y ruido de red de un bloque crudo
- texto_calidad()     <- celda 6: marcas CLIPPED / MAINS_WARN / REST_CHECK_WARN

Cambios respecto del notebook (no tocan los cálculos):
- El simulador recibe REST_CHECK_S y DURACION como argumentos (en el notebook eran
  variables globales), su espera se puede cortar al apretar Detener, y tiene close()
  y version() como el BITalino real.
- texto_calidad() recibe rest_check_passed como argumento (en el notebook era global).

Qué se puede editar aquí: nada; los parámetros están en configuracion.py.
"""

import math
import random
import time

import numpy as np
from scipy.signal import butter, iirnotch, sosfilt, sosfilt_zi, tf2sos, welch

from configuracion import (
    ADC_CLIP_MAX,
    ADC_CLIP_MIN,
    DURACION,
    MAINS_AMPLITUDE_LIMIT_COUNTS,
    MAINS_NOTCH_HZ,
    NOTCH_CASCADA,
    NOTCH_Q,
    QUALITY_FLOOR_BAND_HZ,
    QUALITY_LINE_HALF_BAND_HZ,
    QUALITY_LINE_HZ,
    QUALITY_WELCH_WINDOW_S,
    REST_CHECK_S,
)

VERSION_SIMULADA = "BITalino simulado"


# ---------------------------------------------------------------------------
# Celda 3: simulador
# ---------------------------------------------------------------------------


class BITalinoSimulado:
    MODOS_VALIDOS = {"normal", "fatiga", "contraccion"}

    def __init__(self, semilla=42, velocidad=1.0, modo="normal", rest_check_s=REST_CHECK_S, duracion=DURACION, detener=None):
        self.rng = random.Random(semilla)
        self.velocidad = velocidad
        self.modo = modo.lower()
        self.muestra_actual = 0
        self.fs = None
        self.iniciado = False
        self.rest_check_s = rest_check_s
        self.duracion = duracion
        self.detener = detener  # threading.Event: corta la espera de read()

        if self.modo not in self.MODOS_VALIDOS:
            raise ValueError(f"Modo inválido. Elige uno de: {sorted(self.MODOS_VALIDOS)}")
        if not math.isfinite(self.velocidad) or self.velocidad <= 0:
            raise ValueError("La velocidad debe ser un número mayor que cero.")

    def start(self, frecuencia_muestreo, canales):
        if frecuencia_muestreo <= 0:
            raise ValueError("La frecuencia de muestreo debe ser mayor que cero.")

        self.fs = frecuencia_muestreo
        self.muestra_actual = 0
        self.iniciado = True
        self.inicio_reloj = time.monotonic()

    def read(self, cantidad):
        if not self.iniciado:
            raise RuntimeError("La adquisición simulada no está iniciada.")
        if cantidad < 0:
            raise ValueError("La cantidad de muestras no puede ser negativa.")

        tramas = []
        for _ in range(cantidad):
            t = self.muestra_actual / self.fs
            # Los primeros REST_CHECK_S segundos son reposo (ruido y amplitud mínima): ahí graba la
            # comprobación de reposo, y la adquisición empieza igual. Después sigue el modo elegido.
            t_activo = t - self.rest_check_s
            progreso = (
                min(max(t_activo, 0.0) / (self.duracion - self.rest_check_s), 1.0)
                if self.duracion > self.rest_check_s else 0.0
            )

            if t_activo < 0:
                amplitud = 4
                pesos = [0.5, 1.0, 1.2, 0.8]
            elif self.modo == "fatiga":
                # Amplitud creciente y menor peso de componentes de alta frecuencia.
                amplitud = 25 + 55 * progreso
                pesos = [
                    0.5 + 0.4 * progreso,
                    1.0,
                    1.2 - 0.8 * progreso,
                    0.8 - 0.65 * progreso,
                ]
            elif self.modo == "contraccion":
                # Simula ciclos de 3 s de contracción y 3 s de reposo.
                en_contraccion = (t_activo % 6) < 3
                amplitud = 75 if en_contraccion else 4
                pesos = [0.5, 1.0, 1.2, 0.8]
            else:  # normal
                amplitud = 40
                pesos = [0.5, 1.0, 1.2, 0.8]

            frecuencias = [0.06, 0.12, 0.22, 0.38]
            senal = sum(
                peso * math.sin(2 * math.pi * fraccion * self.fs * t)
                for fraccion, peso in zip(frecuencias, pesos)
            )
            emg_adc = int(
                max(0, min(1023, 512 + amplitud * senal + self.rng.gauss(0, 8)))
            )

            tramas.append([0, 0, 0, 0, 0, emg_adc])
            self.muestra_actual += 1

        tiempo_objetivo = self.muestra_actual / (self.fs * self.velocidad)
        espera = tiempo_objetivo - (time.monotonic() - self.inicio_reloj)
        if espera > 0:
            if self.detener is None:
                time.sleep(espera)
            else:
                self.detener.wait(espera)

        return tramas

    def stop(self):
        self.iniciado = False

    def close(self):
        self.stop()

    def version(self):
        return VERSION_SIMULADA


# ---------------------------------------------------------------------------
# Celda 6: procesador sEMG
# ---------------------------------------------------------------------------


class ProcesadorEMG:
    # Inicializa el procesador con la frecuencia de muestreo especificada.
    def __init__(self, frecuencia_muestreo):
        self.fs = frecuencia_muestreo
        if self.fs <= 800:
            raise ValueError(
                "The 25–400 Hz EMG band requires a sampling rate above 800 Hz."
            )

        # Cada notch se aplica primero; las secciones SOS conservan su estado entre bloques.
        secciones_notch = [
            tf2sos(*iirnotch(frecuencia, Q=NOTCH_Q, fs=self.fs))
            for frecuencia in MAINS_NOTCH_HZ
            for _ in range(NOTCH_CASCADA)
        ]
        sos_bandpass = butter(
            4, [25, 400], btype="bandpass", fs=self.fs, output="sos"
        )
        self.sos = np.vstack((*secciones_notch, sos_bandpass))
        self.estado_filtro = None
        self.ultima_filtrada = np.array([], dtype=float)

    def procesar_bloque(self, muestras):
        valores = np.asarray([float(valor) for _, valor in muestras], dtype=float)
        if valores.size < 32:
            raise ValueError(
                "The EMG block is too short for reliable spectral analysis."
            )
        if self.estado_filtro is None:
            self.estado_filtro = sosfilt_zi(self.sos) * valores[0]
        self.ultima_filtrada, self.estado_filtro = sosfilt(
            self.sos, valores, zi=self.estado_filtro
        )

        rms = float(np.sqrt(np.mean(self.ultima_filtrada ** 2)))
        nperseg = min(valores.size, max(32, round(self.fs * 0.5)))
        frecuencias, potencia = welch(
            self.ultima_filtrada,
            fs=self.fs,
            window="hann",
            nperseg=nperseg,
            noverlap=nperseg // 2,
            detrend="constant",
            scaling="density",
        )
        banda = (frecuencias >= 25) & (frecuencias <= 400)
        frecuencias_banda = frecuencias[banda]
        potencia_banda = potencia[banda]
        potencia_total = float(np.sum(potencia_banda))
        if potencia_total <= 0 or frecuencias_banda.size == 0:
            return rms, float("nan")

        acumulada = np.cumsum(potencia_banda)
        indice = min(
            int(np.searchsorted(acumulada, potencia_total / 2)),
            frecuencias_banda.size - 1,
        )
        if indice == 0:
            mdf = float(frecuencias_banda[0])
        else:
            potencia_previa = acumulada[indice - 1]
            potencia_actual = potencia_banda[indice]
            fraccion = (
                (potencia_total / 2 - potencia_previa) / potencia_actual
                if potencia_actual > 0 else 0.0
            )
            mdf = float(
                frecuencias_banda[indice - 1]
                + fraccion
                * (frecuencias_banda[indice] - frecuencias_banda[indice - 1])
            )
        return rms, mdf


def evaluar_calidad(muestras_crudas, frecuencia_muestreo):
    """Resume clipping y componentes de línea sobre muestras ADC crudas."""
    valores = np.asarray(muestras_crudas, dtype=float)
    if valores.size < 32:
        raise ValueError("Se requieren al menos 32 muestras para evaluar calidad.")
    clipped = (valores <= ADC_CLIP_MIN) | (valores >= ADC_CLIP_MAX)
    nperseg = min(
        valores.size, max(32, round(frecuencia_muestreo * QUALITY_WELCH_WINDOW_S))
    )
    frecuencias, potencia = welch(
        valores, fs=frecuencia_muestreo, nperseg=nperseg,
        noverlap=nperseg // 2, detrend="constant", scaling="density"
    )
    paso_hz = frecuencia_muestreo / nperseg
    lineas = {}
    razones = {}
    frecuencias_lineas = sorted(set(QUALITY_LINE_HZ).union(MAINS_NOTCH_HZ))
    for hz in frecuencias_lineas:
        cerca = np.abs(frecuencias - hz) <= QUALITY_LINE_HALF_BAND_HZ
        piso = (np.abs(frecuencias - hz) >= QUALITY_FLOOR_BAND_HZ[0]) & (
            np.abs(frecuencias - hz) <= QUALITY_FLOOR_BAND_HZ[1]
        )
        lineas[hz] = float(np.sqrt(np.sum(potencia[cerca]) * paso_hz))
        piso_local = float(np.median(potencia[piso])) if np.any(piso) else 0.0
        pico_local = float(np.max(potencia[cerca])) if np.any(cerca) else 0.0
        razones[hz] = (
            pico_local / piso_local if piso_local > 0
            else (float("inf") if pico_local > 0 else float("nan"))
        )
    return {
        "clipped_count": int(np.count_nonzero(clipped)),
        "clipped_percent": float(100 * np.mean(clipped)),
        "line_rms": lineas,
        "peak_ratio": razones,
    }


def texto_calidad(calidad, rest_check_passed):
    marcas = []
    if calidad["clipped_count"]:
        marcas.append(f"CLIPPED:{calidad['clipped_count']}")
    amplitud_maxima = max(
        calidad["line_rms"].get(hz, 0.0) for hz in MAINS_NOTCH_HZ
    )
    if amplitud_maxima > MAINS_AMPLITUDE_LIMIT_COUNTS:
        marcas.append("MAINS_WARN")
    if not rest_check_passed:
        marcas.append("REST_CHECK_WARN")
    return ";".join(marcas) if marcas else "OK"


def dispositivo_es_simulado(dispositivo):
    """True si el dispositivo es el simulador (un PASS con datos simulados no valida el hardware)."""
    return isinstance(dispositivo, BITalinoSimulado)
