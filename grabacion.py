"""
Grabación: réplica de la celda 11 del notebook 4.2 ("Inicio de la adquisición").

Lee bloques de N muestras, calcula RMS y MDF, evalúa la calidad, la actividad y el
índice de fatiga (fatiga.py), y guarda tres CSV en la carpeta de datos, con los mismos
nombres, columnas y numeración que el notebook:
- EMG_TestNN_crudo.csv     señal cruda, una fila por muestra
- EMG_TestNN_bloques.csv   RMS, MDF, actividad e índice de cada bloque
- EMG_TestNN.csv           tendencias cada TREND_INTERVAL_S

Cambios pedidos para la app:
- la grabación sigue hasta que se llama a detener() (el notebook graba DURACION = 10 min);
  por seguridad se corta sola a las DURACION_MAXIMA_S (24 h);
- después de cada bloque avisa a la ventana (función "publicar").

Qué se puede editar aquí: los textos.
"""

import csv
import math
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from configuracion import (
    ADC_CLIP_MAX,
    ADC_CLIP_MIN,
    CANAL,
    DURACION_MAXIMA_S,
    FS,
    MUESTRAS_RECIENTES,
    N,
    PERIODO,
    RAW_WINDOW_S,
    SETTLING_S,
    SOBRESCRIBIR_ARCHIVOS,
    TREND_INTERVAL_S,
)
from fatiga import ENCABEZADO_CRUDO, encabezados
from procesamiento import ProcesadorEMG, dispositivo_es_simulado

PREFIJO = "EMG_Test"


@dataclass
class ArchivosGrabacion:
    tendencias: Path
    crudo: Path
    bloques: Path

    def como_lista(self):
        return [str(self.crudo), str(self.bloques), str(self.tendencias)]


def archivos_siguientes(carpeta, sobrescribir=SOBRESCRIBIR_ARCHIVOS):
    """Nombres de los tres CSV. Igual que la celda 11: el siguiente número EMG_TestNN libre."""
    carpeta = Path(carpeta)
    if sobrescribir:
        prefijo_test = f"{PREFIJO}01"
    else:
        numeros_existentes = []
        for nombre in os.listdir(carpeta):
            if nombre.startswith(PREFIJO):
                numero = nombre[len(PREFIJO):].split("_", 1)[0].split("(", 1)[0]
                if numero.isdigit():
                    numeros_existentes.append(int(numero))
        siguiente_test = max(numeros_existentes, default=0) + 1
        prefijo_test = f"{PREFIJO}{siguiente_test:02d}"
    archivos = ArchivosGrabacion(
        carpeta / f"{prefijo_test}.csv",
        carpeta / f"{prefijo_test}_crudo.csv",
        carpeta / f"{prefijo_test}_bloques.csv",
    )
    if not sobrescribir:
        existentes = [ruta.name for ruta in (archivos.tendencias, archivos.crudo, archivos.bloques) if ruta.exists()]
        if existentes:
            raise FileExistsError(f"Ya existen {existentes}. Revisa los archivos de salida antes de continuar.")
    return archivos


def texto_panel(estado, analizador, dispositivo, archivos):
    """Panel de información. Réplica de actualizar_panel_adquisicion() (celda 8)."""
    texto_muestras = "\n".join(
        f"  t={tiempo:8.3f} s | EMG={valor}"
        for tiempo, valor in estado.muestras_recientes
    ) or "  Todavía no hay muestras."
    texto_trama = repr(estado.ultima_trama)
    if len(texto_trama) > 160:
        texto_trama = texto_trama[:157] + "..."
    indice_fatiga = analizador.ultima_fatiga_intervalo
    texto_fatiga = f"{indice_fatiga:.1f}%" if math.isfinite(indice_fatiga) else "NaN"
    estado_alerta = "ALERTA" if analizador.alerta_fatiga_activada else "Sin alerta"
    return (
        "BITALINO — ADQUISICIÓN Y PROCESAMIENTO\n"
        "======================================\n"
        f"Estado: adquiriendo datos | canal: {CANAL}\n"
        f"Dispositivo: {'SIMULADO' if dispositivo_es_simulado(dispositivo) else 'BITalino'}\n"
        f"PERIODO: {PERIODO} s | FS: {FS:.2f} Hz | DURACION: hasta Detener (máx. {DURACION_MAXIMA_S // 3600} h)\n"
        f"N: {N} | Tendencia: {TREND_INTERVAL_S:g} s\n"
        f"Settling: {SETTLING_S:g} s | Rest check PASS: {analizador.rest_check_passed}\n"
        f"Actividad: {analizador.ultimo_active} | Calidad: {analizador.ultimo_quality_flag}\n"
        f"Fatigue index: {texto_fatiga} | {analizador.ultimo_fatigue_reason}\n"
        f"Alerta: {estado_alerta}\n"
        f"Muestras: {estado.n_medicion}\n"
        f"EMG (ADC): {estado.ultimo_valor_emg} | RMS: {estado.ultimo_rms:.3f}\n"
        f"MDF: {estado.ultimo_mdf:.3f} Hz | Clipped: {estado.clipping_count_recording}\n"
        f"Última trama: {texto_trama}\n"
        f"Últimas {len(estado.muestras_recientes)} muestras:\n{texto_muestras}\n"
        f"CSV crudo: {archivos.crudo.name}\n"
        f"CSV por bloque: {archivos.bloques.name}\n"
        f"CSV tendencias: {archivos.tendencias.name}"
    )


class EstadoGrabacion:
    """Variables de la celda 7 que usa el panel de información (n_medicion, últimos valores...)."""

    def __init__(self):
        self.n_medicion = 0
        self.muestras_recientes = []
        self.ultima_trama = None
        self.ultimo_valor_emg = float("nan")
        self.ultimo_rms = float("nan")
        self.ultimo_mdf = float("nan")
        self.clipping_count_recording = 0
        self.raw_tiempos = deque(maxlen=max(1, int(RAW_WINDOW_S * FS)))
        self.raw_valores = deque(maxlen=max(1, int(RAW_WINDOW_S * FS)))


def grabar(dispositivo, analizador, archivos, detener, publicar=None, duracion_maxima_s=DURACION_MAXIMA_S):
    """
    Graba hasta que se activa 'detener' (threading.Event) o se llega a duracion_maxima_s.
    publicar(estado, resultado, mediciones, resumen_final): se llama después de cada
    bloque (con su ResultadoBloque y sus muestras) y al final (con el último intervalo).
    Devuelve el EstadoGrabacion final.
    """
    estado = EstadoGrabacion()
    procesador_emg = ProcesadorEMG(FS)
    n_mediciones_totales = int(duracion_maxima_s / PERIODO)
    adquisicion_iniciada = False
    try:
        with open(archivos.tendencias, "w", newline="", encoding="utf-8") as archivo_features, \
             open(archivos.crudo, "w", newline="", encoding="utf-8") as archivo_crudo, \
             open(archivos.bloques, "w", newline="", encoding="utf-8") as archivo_bloques:
            encabezado_features, encabezado_bloques = encabezados(analizador.mvc_rms)
            escritor_features = csv.writer(archivo_features)
            escritor_features.writerow(encabezado_features)
            escritor_crudo = csv.writer(archivo_crudo)
            escritor_crudo.writerow(ENCABEZADO_CRUDO)
            escritor_bloques = csv.writer(archivo_bloques)
            escritor_bloques.writerow(encabezado_bloques)
            for archivo in (archivo_features, archivo_crudo, archivo_bloques):
                archivo.flush()

            dispositivo.start(FS, [CANAL])
            adquisicion_iniciada = True
            while estado.n_medicion < n_mediciones_totales and not detener.is_set():
                cantidad = min(N, n_mediciones_totales - estado.n_medicion)
                indice_inicio_bloque = estado.n_medicion
                tramas = dispositivo.read(cantidad)
                mediciones_bloque = []
                raw_rows = []
                for muestra in tramas:
                    indice_muestra = estado.n_medicion
                    estado.n_medicion += 1
                    tiempo = indice_muestra * PERIODO
                    valor = int(muestra[5])
                    asentamiento_muestra = tiempo < SETTLING_S
                    calidad_muestra = (
                        "CLIPPED" if valor <= ADC_CLIP_MIN or valor >= ADC_CLIP_MAX else "OK"
                    )
                    estado.clipping_count_recording += int(calidad_muestra == "CLIPPED")
                    estado.ultima_trama = muestra
                    estado.ultimo_valor_emg = valor
                    estado.muestras_recientes.append((tiempo, valor))
                    estado.muestras_recientes[:] = estado.muestras_recientes[-MUESTRAS_RECIENTES:]
                    estado.raw_tiempos.append(tiempo)
                    estado.raw_valores.append(valor)
                    mediciones_bloque.append((tiempo, valor))
                    raw_rows.append([tiempo, valor, asentamiento_muestra, calidad_muestra])
                if not mediciones_bloque:
                    continue
                escritor_crudo.writerows(raw_rows)
                archivo_crudo.flush()
                rms, mdf = procesador_emg.procesar_bloque(mediciones_bloque)
                estado.ultimo_rms, estado.ultimo_mdf = rms, mdf
                resultado = analizador.procesar_bloque(indice_inicio_bloque, mediciones_bloque, rms, mdf)
                escritor_bloques.writerow(resultado.fila)
                archivo_bloques.flush()
                if resultado.resumen is not None:
                    escritor_features.writerow(resultado.resumen.fila)
                    archivo_features.flush()
                if publicar:
                    publicar(estado, resultado, mediciones_bloque, None)

            final = analizador.cerrar_intervalo()
            if final is not None:
                escritor_features.writerow(final.fila)
                archivo_features.flush()
                if publicar:
                    publicar(estado, None, [], final)
    finally:
        if adquisicion_iniciada:
            dispositivo.stop()
    return estado
