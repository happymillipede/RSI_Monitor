"""
Ciclo de medición: lee bloques del dispositivo (BITalino real o simulado), calcula
RMS y MDF con ProcesadorEMG del original, los agrupa con ReglaFatiga y guarda el CSV.

Es una réplica de la celda "Adquisición de sEMG" de Código_Bitalino_Python.py
(líneas 380-447), con tres cambios pedidos para la app:
- la medición dura hasta que se llama detener() (el original mide DURACION = 120 s);
- el CSV lleva fecha y hora en el nombre (uno por sesión);
- con el BITalino real, si se pierde la conexión se vuelve a conectar sin cortar la
  sesión (se mantienen la línea base y el CSV).

- SesionMedicion: el ciclo en Python puro. Avisa lo que pasa a un "oyente" (ver la
  clase Oyente). El modo --headless usa un oyente que imprime.
- HiloAdquisicion: corre SesionMedicion en un QThread, para que la ventana nunca se
  congele, y convierte los avisos en señales Qt.

Qué se puede editar aquí: ENCABEZADO_CSV y MUESTRAS_RECIENTES.
"""

import csv
import queue
import statistics
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from nucleo.regla_fatiga import ReglaFatiga
from nucleo.simulador import COLUMNA_EMG

ENCABEZADO_CSV = ["Time (s)", "Mean RMS (ADC)", "Median MDF (Hz)"]  # línea 386
MUESTRAS_RECIENTES = 8  # línea 411: el panel muestra las últimas 8 muestras
FORMATO_FECHA_CSV = "%Y-%m-%d_%H-%M-%S"

# Estados de la medición que se muestran en la ventana
DESCONECTADO = "Desconectado"
BUSCANDO = "Buscando"
CONECTANDO = "Conectando"
CALIBRANDO = "Calibrando línea base"
MIDIENDO = "Midiendo"
ERROR = "Error"


@dataclass
class InfoBloque:
    """Datos del panel de información, los mismos de actualizar_panel_adquisicion()."""

    n_medicion: int
    ultimo_valor_emg: float
    ultimo_rms: float
    ultimo_mdf: float
    ultima_trama: object
    muestras_recientes: list = field(default_factory=list)


class Oyente:
    """Recibe los avisos de la sesión. Por defecto no hace nada; se reemplazan los que se necesiten."""

    def al_cambiar_estado(self, estado, detalle=""):
        pass

    def al_procesar_bloque(self, info):
        pass

    def al_cerrar_intervalo(self, resumen, linea_base):
        pass

    def al_detectar_fatiga(self, resumen):
        pass

    def al_conectar(self, puerto):
        pass


def cerrar_dispositivo(dispositivo, adquisicion_iniciada):
    """device.stop() y close(). Si el dispositivo ya se desconectó pueden fallar: se ignora."""
    try:
        if adquisicion_iniciada:
            dispositivo.stop()
    except Exception:
        pass
    try:
        dispositivo.close()
    except Exception:
        pass


def nombre_csv(prefijo, fecha):
    """Ej.: EMG_features_2026-11-06_10-30-00.csv"""
    return f"{prefijo}_{fecha.strftime(FORMATO_FECHA_CSV)}.csv"


def prefijo_csv(constantes, simulacion):
    """Usa los nombres del original: "EMG_features" (línea 185) o "EMG_simulated_features" (línea 471)."""
    if simulacion:
        return Path(constantes.get("SIM_OUTPUT_CSV", "EMG_simulated_features.csv")).stem
    return Path(constantes.get("archivo_features_csv", "EMG_features.csv")).stem


class SesionMedicion:
    def __init__(
        self, original, parametros, abrir_dispositivo, carpeta_datos, prefijo_csv, oyente=None, reconectar=False
    ):
        """
        original: CodigoOriginal (ProcesadorEMG y constantes).
        parametros: parámetros de detección (TREND_INTERVAL_S, umbrales, etc.).
        abrir_dispositivo(detener, avisar): función que devuelve un dispositivo listo para
            start(), o None si se pidió detener mientras se conectaba. "detener" es un
            threading.Event y "avisar(estado, detalle)" sirve para mostrar el avance.
        carpeta_datos: dónde se guarda el CSV de la sesión.
        prefijo_csv: inicio del nombre del CSV (ej. "EMG_features").
        reconectar: True con el BITalino real (si falla una lectura, se vuelve a conectar).
        """
        self.original = original
        self.constantes = original.constantes
        self.abrir_dispositivo = abrir_dispositivo
        self.reconectar = reconectar
        self.oyente = oyente or Oyente()
        self.ruta_csv = Path(carpeta_datos) / nombre_csv(prefijo_csv, datetime.now())

        self.regla = ReglaFatiga.desde_parametros(parametros)
        self.procesador_emg = original.ProcesadorEMG(original.fs)  # línea 324

        # Líneas 321 y 327-331
        self.n_medicion = 0
        self.muestras_recientes = []
        self.ultima_trama = None
        self.ultimo_valor_emg = float("nan")
        self.ultimo_rms = float("nan")
        self.ultimo_mdf = float("nan")

        self.estado = DESCONECTADO
        self.pedido_detener = threading.Event()
        self.comandos = queue.SimpleQueue()

    # --- Órdenes que llegan desde otro hilo (la ventana). Se aplican antes del bloque siguiente. ---

    def detener(self):
        self.pedido_detener.set()

    def pausar_alertas(self, pausar):
        """Durante un descanso no se evalúa la fatiga."""
        self.comandos.put(("pausar", pausar))

    def rearmar_alerta(self):
        """Al terminar un descanso la alerta vuelve a estar disponible."""
        self.comandos.put(("rearmar", None))

    def aplicar_comandos(self):
        while not self.comandos.empty():
            orden, valor = self.comandos.get()
            if orden == "pausar":
                self.regla.pausada = valor
            elif orden == "rearmar":
                self.regla.rearmar()

    # --- Ciclo de medición ---

    def cambiar_estado(self, estado, detalle=""):
        self.estado = estado
        self.oyente.al_cambiar_estado(estado, detalle)

    def ejecutar(self):
        """Mide hasta que se llame detener(). Réplica de las líneas 380-447."""
        dispositivo = None
        adquisicion_iniciada = False
        try:
            # Primero se conecta, para no dejar un CSV vacío si no hay dispositivo.
            self.cambiar_estado(CONECTANDO)
            dispositivo = self.abrir_dispositivo(self.pedido_detener, self.cambiar_estado)
            if dispositivo is None:  # se pidió detener mientras se conectaba
                return
            self.avisar_conexion(dispositivo)

            with open(self.ruta_csv, "w", newline="", encoding="utf-8") as archivo_features:
                escritor_features = csv.writer(archivo_features)
                escritor_features.writerow(ENCABEZADO_CSV)
                archivo_features.flush()

                # Línea 391
                dispositivo.start(self.original.fs, [self.constantes["CANAL"]])
                adquisicion_iniciada = True
                self.cambiar_estado(CALIBRANDO)

                while not self.pedido_detener.is_set():
                    self.aplicar_comandos()
                    try:
                        trama = dispositivo.read(self.constantes["N"])
                    except Exception as error:
                        if not self.reconectar:
                            raise
                        dispositivo = self.volver_a_conectar(dispositivo, error)
                        if dispositivo is None:  # se pidió detener mientras se reconectaba
                            break
                        continue
                    self.procesar_trama(trama, escritor_features, archivo_features)

                # Línea 443: guardar el intervalo final, incluso si está incompleto
                self.cerrar_intervalo(escritor_features, archivo_features)

        except Exception as error:
            self.cambiar_estado(ERROR, str(error))
            raise

        finally:
            # Líneas 445-447 (además se cierra el puerto para poder volver a conectar)
            if dispositivo is not None:
                cerrar_dispositivo(dispositivo, adquisicion_iniciada)
            if self.estado != ERROR:
                self.cambiar_estado(DESCONECTADO)

    def avisar_conexion(self, dispositivo):
        puerto = getattr(dispositivo, "puerto", None)  # el simulado no tiene puerto
        if puerto:
            self.oyente.al_conectar(puerto)

    def volver_a_conectar(self, dispositivo, error):
        """
        Se perdió la conexión: cierra el puerto y busca el BITalino de nuevo hasta
        encontrarlo (o hasta que se pida detener). Devuelve el dispositivo ya iniciado, o None.
        """
        cerrar_dispositivo(dispositivo, adquisicion_iniciada=True)
        self.cambiar_estado(CONECTANDO, f"Se perdió la conexión ({error}). Reconectando…")
        while not self.pedido_detener.is_set():
            nuevo = self.abrir_dispositivo(self.pedido_detener, self.cambiar_estado)
            if nuevo is None:
                return None
            try:
                nuevo.start(self.original.fs, [self.constantes["CANAL"]])
            except Exception as error_inicio:
                cerrar_dispositivo(nuevo, adquisicion_iniciada=False)
                self.cambiar_estado(CONECTANDO, f"No se pudo iniciar la adquisición ({error_inicio}).")
                continue
            self.avisar_conexion(nuevo)
            # Filtro nuevo: parte del primer valor del bloque siguiente, igual que al
            # encender (línea 92 del original), sin arrastrar la señal de antes del corte.
            self.procesador_emg = self.original.ProcesadorEMG(self.original.fs)
            self.cambiar_estado(CALIBRANDO if self.regla.calibrando() else MIDIENDO)
            return nuevo
        return None

    def procesar_trama(self, trama, escritor_features, archivo_features):
        """Procesa un bloque leído del dispositivo (líneas 400-440)."""
        periodo = self.constantes["PERIODO"]
        mediciones_bloque = []

        for muestra in trama:
            self.n_medicion += 1
            tiempo = self.n_medicion * periodo
            valor = int(muestra[COLUMNA_EMG])

            self.ultima_trama = muestra
            self.ultimo_valor_emg = valor
            self.muestras_recientes.append((tiempo, valor))
            self.muestras_recientes[:] = self.muestras_recientes[-MUESTRAS_RECIENTES:]

            mediciones_bloque.append([tiempo, valor])

        if not mediciones_bloque:
            return

        tiempos_bloque = [tiempo for tiempo, _ in mediciones_bloque]
        rms, mdf = self.procesador_emg.procesar_bloque(mediciones_bloque)
        self.ultimo_rms = rms
        self.ultimo_mdf = mdf
        self.oyente.al_procesar_bloque(self.info_bloque())

        tiempo_bloque = statistics.mean(tiempos_bloque)
        resumen = self.regla.agregar_bloque(tiempo_bloque, rms, mdf)
        if resumen is not None:
            self.registrar_resumen(resumen, escritor_features, archivo_features)

    def cerrar_intervalo(self, escritor_features, archivo_features):
        resumen = self.regla.cerrar_intervalo()
        if resumen is not None:
            self.registrar_resumen(resumen, escritor_features, archivo_features)

    def registrar_resumen(self, resumen, escritor_features, archivo_features):
        """Guarda el resumen en el CSV (líneas 291-294) y avisa al oyente."""
        escritor_features.writerow([resumen.tiempo, resumen.rms, resumen.mdf])
        archivo_features.flush()

        if self.estado == CALIBRANDO and not self.regla.calibrando():
            self.cambiar_estado(MIDIENDO)

        self.oyente.al_cerrar_intervalo(resumen, self.regla.linea_base())
        if resumen.alerta:
            self.oyente.al_detectar_fatiga(resumen)

    def info_bloque(self):
        return InfoBloque(
            n_medicion=self.n_medicion,
            ultimo_valor_emg=self.ultimo_valor_emg,
            ultimo_rms=self.ultimo_rms,
            ultimo_mdf=self.ultimo_mdf,
            ultima_trama=self.ultima_trama,
            muestras_recientes=list(self.muestras_recientes),
        )


class HiloAdquisicion(QThread):
    """
    Corre una SesionMedicion en un hilo aparte. La ventana se conecta a estas señales;
    Qt las entrega en el hilo de la ventana, así que ahí se puede tocar la interfaz.
    """

    estado_cambiado = Signal(str, str)  # estado, detalle
    bloque_procesado = Signal(object)  # InfoBloque
    intervalo_cerrado = Signal(object, object)  # ResumenIntervalo, línea base (o None)
    fatiga_detectada = Signal(object)  # ResumenIntervalo
    puerto_conectado = Signal(str)  # puerto del BITalino que respondió

    def __init__(self, sesion):
        super().__init__()
        self.sesion = sesion
        sesion.oyente = self

    def run(self):
        try:
            self.sesion.ejecutar()
        except Exception:
            # La sesión ya avisó el estado Error con el detalle; aquí solo se deja el rastro.
            traceback.print_exc()

    # Órdenes desde la ventana
    def detener(self):
        self.sesion.detener()

    def pausar_alertas(self, pausar):
        self.sesion.pausar_alertas(pausar)

    def rearmar_alerta(self):
        self.sesion.rearmar_alerta()

    # Avisos de la sesión (corren en el hilo de medición) -> señales
    def al_cambiar_estado(self, estado, detalle=""):
        self.estado_cambiado.emit(estado, detalle)

    def al_procesar_bloque(self, info):
        self.bloque_procesado.emit(info)

    def al_cerrar_intervalo(self, resumen, linea_base):
        self.intervalo_cerrado.emit(resumen, linea_base)

    def al_detectar_fatiga(self, resumen):
        self.fatiga_detectada.emit(resumen)

    def al_conectar(self, puerto):
        self.puerto_conectado.emit(puerto)
