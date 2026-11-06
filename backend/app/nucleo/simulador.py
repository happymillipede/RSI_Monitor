"""
BITalino simulado: genera una señal EMG sintética para probar la app sin hardware.

DispositivoSimulado tiene la misma interfaz que bitalino.BITalino:
    start(fs, canales), read(n) -> array (n, 6) con el valor ADC en la columna 5,
    stop(), close() y version().
Así el mismo ciclo de adquisición sirve para el dispositivo real y el simulado.

La señal es una réplica fiel de la celda "Synthetic EMG trend test" del original
(Código_Bitalino_Python.py, líneas 519-655): ruido blanco filtrado en 30-350 Hz
(señal "normal") y en 30-180 Hz (señal "de baja frecuencia"). En el escenario
"fatigue_test" se mezclan de forma progresiva y sube la amplitud.

Diferencia con el original: entrega las muestras a ritmo real (1 bloque de 1000
muestras por segundo), con un multiplicador de velocidad opcional (x1, x10).

Qué se puede editar aquí: las constantes de abajo (son las cifras fijas que usa
el original dentro de la celda de simulación).
"""

import time

import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi

# Cifras fijas de la celda de simulación del original:
ESCENARIOS = ("normal", "fatigue_test")  # línea 481
ORDEN_FILTRO = 4  # líneas 520-525
BANDA_NORMAL_HZ = [30, 350]  # línea 521
BANDA_BAJA_FRECUENCIA_HZ = [30, 180]  # línea 524
SEMILLA = 42  # línea 544: np.random.default_rng(42)
DURACION_RAMPA_S = 15  # línea 631: la mezcla tarda 15 s en completarse
AMPLITUD_BASE = 20  # línea 638
AUMENTO_AMPLITUD = 0.5  # línea 638: la amplitud sube hasta 1.5 veces
NIVEL_CERO_ADC = 512  # línea 645: centro del ADC de 10 bits
ADC_MINIMO = 0  # línea 645
ADC_MAXIMO = 1023  # línea 645

# Forma de la trama, igual que bitalino.BITalino.read() con un canal analógico:
# columna 0 = número de secuencia (0-15), columnas 1-4 = digitales, columna 5 = EMG.
COLUMNAS_TRAMA = 6
COLUMNA_EMG = 5
MAXIMO_SECUENCIA = 16

VERSION_SIMULADA = "BITalino_v5.2 (simulado)"


def filtrar_continuo(sos, estado, valores):
    """Réplica de filter_continuously() (líneas 529-534)."""
    if estado is None:
        estado = sosfilt_zi(sos) * valores[0]

    filtrada, estado = sosfilt(sos, valores, zi=estado)
    return filtrada, estado


class DispositivoSimulado:
    def __init__(self, escenario, fs, inicio_rampa_s, velocidad=1, reloj=time.monotonic, dormir=time.sleep):
        """
        escenario: "normal" o "fatigue_test".
        fs: frecuencia de muestreo (Hz).
        inicio_rampa_s: segundo en que empieza la mezcla (el original usa SIM_BASELINE_DURATION_S).
        velocidad: 1 = tiempo real, 10 = diez veces más rápido, None = sin esperar (pruebas).
        """
        # Líneas 475-482
        if fs <= 800:
            raise ValueError(
                "La simulación necesita FS > 800 Hz porque el procesador EMG usa la banda 25-400 Hz."
            )
        if escenario not in ESCENARIOS:
            raise ValueError("El escenario debe ser 'normal' o 'fatigue_test'.")

        self.escenario = escenario
        self.fs = fs
        self.inicio_rampa_s = inicio_rampa_s
        self.velocidad = velocidad
        self.reloj = reloj
        self.dormir = dormir

        # Líneas 520-527
        self.sos_normal = butter(ORDEN_FILTRO, BANDA_NORMAL_HZ, btype="bandpass", fs=fs, output="sos")
        self.sos_baja_frecuencia = butter(
            ORDEN_FILTRO, BANDA_BAJA_FRECUENCIA_HZ, btype="bandpass", fs=fs, output="sos"
        )
        self.estado_normal = None
        self.estado_baja_frecuencia = None

        self.rng = np.random.default_rng(SEMILLA)  # línea 544
        self.muestras_generadas = 0
        self.iniciado = False
        self.instante_inicio = None

    def version(self):
        return VERSION_SIMULADA

    def start(self, fs=1000, canales=(0,)):
        self.iniciado = True
        self.instante_inicio = self.reloj()

    def stop(self):
        self.iniciado = False

    def close(self):
        pass

    def read(self, n):
        """Devuelve n muestras con la misma forma que bitalino.BITalino.read()."""
        if not self.iniciado:
            raise Exception("The device is not in acquisition mode.")

        primera = self.muestras_generadas
        valores_adc = self.generar(n)

        trama = np.zeros((n, COLUMNAS_TRAMA), dtype=int)
        trama[:, 0] = np.arange(primera, primera + n) % MAXIMO_SECUENCIA
        trama[:, COLUMNA_EMG] = valores_adc

        self.esperar_ritmo_real()
        return trama

    def generar(self, n):
        """Genera n valores ADC (réplica de las líneas 615-646)."""
        ruido_blanco = self.rng.normal(0, 1, n)

        senal_normal, self.estado_normal = filtrar_continuo(
            self.sos_normal, self.estado_normal, ruido_blanco
        )
        senal_baja, self.estado_baja_frecuencia = filtrar_continuo(
            self.sos_baja_frecuencia, self.estado_baja_frecuencia, ruido_blanco
        )

        inicio_bloque_s = self.muestras_generadas / self.fs

        if self.escenario == "fatigue_test":
            # Sube la amplitud y baja el contenido de frecuencia después de la línea base.
            progresion = np.clip(
                (inicio_bloque_s - self.inicio_rampa_s) / DURACION_RAMPA_S,
                0,
                1,
            )
        else:
            progresion = 0

        amplitud = AMPLITUD_BASE * (1 + AUMENTO_AMPLITUD * progresion)
        senal = (1 - progresion) * senal_normal + progresion * senal_baja

        valores_adc = np.clip(
            np.rint(NIVEL_CERO_ADC + amplitud * senal), ADC_MINIMO, ADC_MAXIMO
        ).astype(int)

        self.muestras_generadas += n
        return valores_adc

    def esperar_ritmo_real(self):
        """Espera hasta que, en tiempo real (dividido por la velocidad), hayan pasado las muestras entregadas."""
        if not self.velocidad:
            return
        segundos_de_senal = self.muestras_generadas / self.fs
        objetivo = self.instante_inicio + segundos_de_senal / self.velocidad
        espera = objetivo - self.reloj()
        if espera > 0:
            self.dormir(espera)
