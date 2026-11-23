"""
Parámetros de RSI Monitor.

1. Copia de la configuración del notebook del grupo, originales/bitalino_codigo (Ver 4.2).ipynb:
   celda 2 ("Configuración del Bitalino"), celda 3 (simulador) y celda 7 (ventanas de
   los gráficos). Mismos nombres y valores. Si el grupo cambia un valor en el notebook,
   hay que cambiarlo aquí también: tests/test_configuracion.py lo compara con el
   notebook y avisa si no coinciden.
2. Parámetros propios de la app (duración máxima, alerta, carpetas).
3. Ajustes que el usuario cambia en la ventana (datos/ajustes.json).

Qué se puede editar aquí: todo. Los valores de la parte 1 deben seguir al notebook.
"""

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Notebook 4.2, celda 2: configuración del BITalino
# ---------------------------------------------------------------------------

PUERTO = "/dev/tty.bitalino"  # Puerto Bluetooth correspondiente al Bitalino
CANAL = 0  # A1 = 0, A2 = 1, A3 = 2, etc...
PERIODO = 0.001  # 1000 Hz
N = 1000  # Número de mediciones por bloque
# En el notebook, DURACION es lo que dura la grabación. En la app la grabación sigue
# hasta apretar Detener (máximo DURACION_MAXIMA_S); DURACION solo la usa el simulador
# para saber en cuánto tiempo llega a la fatiga máxima.
DURACION = 10 * 60

# Parámetros de procesamiento y calidad de señal
MAINS_NOTCH_HZ = (50.0, 100.0, 150.0, 250.0)  # Red de 50 Hz y armónicas observadas en las grabaciones
NOTCH_Q = 30.0
NOTCH_CASCADA = 2  # Notches idénticos en cascada por frecuencia
ADC_CLIP_MIN = 0
ADC_CLIP_MAX = 1023
QUALITY_LINE_HZ = (50.0, 100.0, 150.0, 250.0)
QUALITY_LINE_HALF_BAND_HZ = 2.0
QUALITY_FLOOR_BAND_HZ = (3.0, 10.0)
QUALITY_WELCH_WINDOW_S = 2.0
HUM_CHECK_BAND_HZ = (145.0, 155.0)
HUM_RESIDUAL_BAND_HZ = 5.0  # Banda ± alrededor de cada armónica para medir ruido de red residual
SETTLING_S = 2.0  # Con la cascada de notches el transitorio dura ~2 s
REST_CHECK_S = 15.0
MAINS_AMPLITUDE_LIMIT_COUNTS = 100.0  # PROVISIONAL: calibrar después de las primeras grabaciones limpias
RMS_ACTIVE_K = 3.0
RMS_ACTIVE_MIN_RATIO = 3.0  # Umbral Active = max(mediana + K·SD, RATIO × mediana)
REST_MAX_MIN_RATIO = 4.0  # PROVISIONAL: bloque de reposo máx/mín permitido
RMS_FALLBACK_INIT_S = 5.0

# Parámetros de tendencia y fatiga
TREND_INTERVAL_S = 5.0
BASELINE_ACTIVE_S = 10.0
RMS_INCREASE_THRESHOLD = 0.20  # Sin validar: calibrar con contracciones sostenidas a %MVC fijo
MDF_DECREASE_THRESHOLD = 0.15  # Sin validar: calibrar con contracciones sostenidas a %MVC fijo
USE_SLOPE_TEST = True
SLOPE_WINDOW_S = 20.0
SLOPE_P_THRESHOLD = 0.05
SLOPE_MIN_POINTS = 5  # Mínimo de bloques Active dentro de la ventana
SLOPE_MIN_SPAN_FRACTION = 0.75  # Los bloques Active deben cubrir al menos esta fracción de SLOPE_WINDOW_S
FATIGUE_ALERT_THRESHOLD = 60.0  # Sin validar. Valor inicial del "Porcentaje de alerta"

# Parámetros opcionales de MVC
MVC_S = 5.0  # Duración de cada contracción máxima (los primeros SETTLING_S no cuentan)
MVC_TRIALS = 3  # Ensayos; MVC_RMS = el bloque de 1 s con mayor RMS de todos
MVC_REST_S = 30.0  # Descanso entre ensayos
MVC_COUNTDOWN_S = 3  # Cuenta regresiva antes de cada ensayo
SOBRESCRIBIR_ARCHIVOS = False  # Si es False, cada grabación usa el siguiente número EMG_TestNN disponible

# ---------------------------------------------------------------------------
# Notebook 4.2, celda 3: simulador
# ---------------------------------------------------------------------------

VELOCIDAD_SIMULACION = 1.0  # 1.0 = tiempo real; 2.0 = doble de rápida, etc
MODO_EMG = "fatiga"  # "normal", "fatiga" o "contraccion"

# ---------------------------------------------------------------------------
# Notebook 4.2, celda 7: ventanas de los gráficos
# ---------------------------------------------------------------------------

TREND_WINDOW_S = 30  # segundos visibles en las tendencias
RAW_WINDOW_S = 5  # segundos visibles de señal cruda
BLOCK_WINDOW_S = 30  # segundos visibles de RMS y MDF por bloque

FS = 1 / PERIODO

# ---------------------------------------------------------------------------
# 2. Parámetros propios de la app
# ---------------------------------------------------------------------------

NOMBRE_APP = "RSI Monitor"
# La grabación sigue hasta apretar Detener. Por seguridad se corta sola a las 24 h.
DURACION_MAXIMA_S = 24 * 60 * 60
# Después de cerrar el pop-up, la alerta vuelve a estar disponible pasados estos minutos.
REARME_ALERTA_MIN = 10
VELOCIDADES_SIMULACION = (1, 5, 10)  # opciones del selector (×1 = tiempo real)
TIEMPO_LIMITE_CONEXION_S = 10  # segundos máximos para que el BITalino responda
MUESTRAS_RECIENTES = 8  # el panel muestra las últimas 8 muestras, como el notebook

# Carpeta de la app y carpeta de datos (CSV y ajustes).
# Empaquetada con PyInstaller, los archivos de la interfaz quedan en sys._MEIPASS y los
# datos junto al .exe (Windows) o en Documentos/RSI_Monitor (macOS, porque escribir
# dentro de la .app la rompe).
EMPAQUETADA = getattr(sys, "frozen", False)
CARPETA_APP = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
CARPETA_INTERFAZ = CARPETA_APP / "interfaz"
if EMPAQUETADA and sys.platform == "darwin":
    CARPETA_DATOS = Path.home() / "Documents" / "RSI_Monitor"
elif EMPAQUETADA:
    CARPETA_DATOS = Path(sys.executable).resolve().parent / "datos"
else:
    CARPETA_DATOS = Path(__file__).resolve().parent / "datos"

# ---------------------------------------------------------------------------
# 3. Ajustes que se cambian desde la ventana (datos/ajustes.json)
# ---------------------------------------------------------------------------

NOMBRE_AJUSTES = "ajustes.json"
AJUSTES_POR_DEFECTO = {
    "umbral_alerta": FATIGUE_ALERT_THRESHOLD,  # "Porcentaje de alerta" (%)
    "rearme_alerta_min": REARME_ALERTA_MIN,
    "ultimo_puerto": None,  # el último puerto que funcionó; se prueba primero
    "modo_simulacion": MODO_EMG,
    "velocidad_simulacion": VELOCIDAD_SIMULACION,
}


def leer_ajustes(carpeta=None):
    """Ajustes guardados; lo que falte (o un archivo dañado) usa AJUSTES_POR_DEFECTO."""
    ruta = Path(carpeta or CARPETA_DATOS) / NOMBRE_AJUSTES
    ajustes = dict(AJUSTES_POR_DEFECTO)
    try:
        ajustes.update(json.loads(ruta.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return ajustes


def guardar_ajustes(ajustes, carpeta=None):
    carpeta = Path(carpeta or CARPETA_DATOS)
    carpeta.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(ajustes, indent=2, ensure_ascii=False)
    (carpeta / NOMBRE_AJUSTES).write_text(texto + "\n", encoding="utf-8")
