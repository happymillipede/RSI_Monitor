"""
Formato de los mensajes entre el backend y el frontend (modelos Pydantic).

- Mensajes del WebSocket (/ws): todos tienen un campo "tipo". Al conectarse, el
  navegador recibe primero un MensajeEstado (la foto completa) y después los demás.
- Pedidos y respuestas de la API REST (/api/...).

Este archivo es la referencia: frontend/lib/tipos.ts lo copia a mano. Si cambian un
campo aquí, cámbienlo también allá y en la tabla del README.

Los números que pueden faltar (NaN en el original, ej. la MDF de un bloque sin
potencia) van como null en el JSON.

Qué se puede editar aquí: los campos, siempre junto con frontend/lib/tipos.ts.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

Modo = Literal["real", "simulacion"]
Escenario = Literal["normal", "fatigue_test"]
EstadoConexion = Literal["Desconectado", "Buscando", "Conectando", "Conectado", "Error"]

# --- Partes que se repiten en varios mensajes ---


class PuntoTendencia(BaseModel):
    """Una fila del CSV: Time (s), Mean RMS (ADC), Median MDF (Hz)."""

    tiempo: float
    rms: Optional[float]
    mdf: Optional[float]


class Muestra(BaseModel):
    tiempo: float
    valor: int


class Bloque(BaseModel):
    """Datos del panel de información, uno por bloque de N muestras."""

    n_medicion: int
    ultimo_valor_emg: Optional[float]
    ultimo_rms: Optional[float]
    ultimo_mdf: Optional[float]
    muestras_recientes: list[Muestra]
    texto_panel: str  # el panel completo, con el formato de actualizar_panel_adquisicion()


class LineaBase(BaseModel):
    rms: float
    mdf: float
    texto: str


class Calibracion(BaseModel):
    calibrando: bool
    texto: str  # "Calibrando línea base (N s): ..."
    linea_base: Optional[LineaBase]


class Parametros(BaseModel):
    """Parámetros de detección en uso (nombres del original)."""

    TREND_INTERVAL_S: float
    TREND_WINDOW_S: float
    BASELINE_DURATION_S: float
    ALERT_PERSISTENCE_S: float
    RMS_INCREASE_THRESHOLD: float
    MDF_DECREASE_THRESHOLD: float


class InfoConexion(BaseModel):
    estado: EstadoConexion
    puerto: Optional[str]
    version: Optional[str]
    detalle: str  # qué está pasando o el último error, en palabras simples
    en_docker: bool  # True: el modo real no está disponible


class InfoMedicion(BaseModel):
    encendida: bool
    modo_preferido: Modo  # el que el botón Encender propone (simulación en Docker o con --sim)
    modo: Optional[Modo]
    escenario: Optional[Escenario]
    velocidad: Optional[float]
    umbrales_sim: bool
    estado: str  # estado de la medición: Conectando, Calibrando línea base, Midiendo...
    ruta_csv: Optional[str]


class InfoAlerta(BaseModel):
    pendiente: bool
    texto: str  # "Riesgo de fatiga muscular, descanse X minutos"
    aclaracion: str  # no es un diagnóstico médico
    minutos: float


class InfoDescanso(BaseModel):
    activo: bool
    nombre: Optional[str]
    origen: Optional[Literal["fatiga", "manual"]]
    duracion_planeada_s: float
    segundos_restantes: float
    minutos_hoy: float  # total de descansos de hoy
    cantidad_hoy: int


class InfoReloj(BaseModel):
    segundos_hoy: float
    segundos_sesion: float
    texto_hoy: str  # ej. "1:02:05"
    texto_sesion: str
    corriendo: bool


# --- Mensajes del WebSocket ---


class MensajeEstado(BaseModel):
    """Foto completa. Se envía al conectarse y al encender o apagar la medición."""

    tipo: Literal["estado"] = "estado"
    estado_app: str
    medicion: InfoMedicion
    conexion: InfoConexion
    parametros: Parametros
    calibracion: Calibracion
    tendencia: list[PuntoTendencia]
    ultimo_bloque: Optional[Bloque]
    alerta: InfoAlerta
    descanso: InfoDescanso
    reloj: InfoReloj


class MensajeConexion(BaseModel):
    """Cambió el estado de la conexión o de la medición."""

    tipo: Literal["conexion"] = "conexion"
    estado_app: str
    medicion: InfoMedicion
    conexion: InfoConexion


class MensajeBloque(BaseModel):
    tipo: Literal["bloque"] = "bloque"
    bloque: Bloque


class MensajeTendencia(BaseModel):
    """Un punto nuevo por intervalo de tendencia."""

    tipo: Literal["tendencia"] = "tendencia"
    estado_app: str
    punto: PuntoTendencia
    calibracion: Calibracion


class MensajeAlerta(BaseModel):
    tipo: Literal["alerta"] = "alerta"
    estado_app: str
    alerta: InfoAlerta


class MensajeDescanso(BaseModel):
    tipo: Literal["descanso"] = "descanso"
    estado_app: str
    evento: Literal["iniciado", "terminado"]
    completado: bool  # con evento "terminado": True si se cumplió el tiempo
    descanso: InfoDescanso


class MensajeReloj(BaseModel):
    """Una vez por segundo."""

    tipo: Literal["reloj"] = "reloj"
    reloj: InfoReloj
    segundos_restantes_descanso: float


# --- Pedidos a la API REST ---


class PedidoEncender(BaseModel):
    modo: Modo
    escenario: Optional[Escenario] = None  # None = el de config.json (o SIM_SCENARIO)
    velocidad: Optional[float] = Field(None, ge=0)  # 0 = sin esperar (solo pruebas)
    umbrales_sim: Optional[bool] = None


class PedidoDescanso(BaseModel):
    """Una plantilla (su índice) o una duración libre en minutos."""

    plantilla: Optional[int] = None
    minutos: Optional[float] = None


class Plantilla(BaseModel):
    nombre: str
    duracion_min: float


class PedidoConfig(BaseModel):
    """Solo se cambia lo que viene. En 'parametros', null = volver al valor del original."""

    parametros: Optional[dict[str, Optional[float]]] = None
    duracion_fatiga_min: Optional[float] = None
    usar_umbrales_sim: Optional[bool] = None
    restaurar: bool = False  # True: los parámetros vuelven al original y el descanso, al de config.ejemplo.json


class PedidoReconectar(BaseModel):
    puerto: Optional[str] = None  # None = detectar automáticamente


# --- Respuestas de la API REST ---


class ParametroConfig(BaseModel):
    nombre: str
    valor: float  # el que se usa
    original: float  # el de Código_Bitalino_Python.py
    sim: float  # el SIM_* del original
    personalizado: bool  # True si el usuario lo cambió
    minimo: float
    maximo: float


class RespuestaConfig(BaseModel):
    parametros: list[ParametroConfig]
    duracion_fatiga_min: float
    usar_umbrales_sim: bool
    velocidades: list[float]
    TREND_WINDOW_S: float


class RespuestaPlantillas(BaseModel):
    plantillas: list[Plantilla]


class RegistroDescanso(BaseModel):
    """Así queda cada descanso en datos/descansos.json."""

    nombre: str
    origen: Literal["fatiga", "manual"]
    inicio: str
    fin: str
    duracion_planeada_min: float
    duracion_real_min: float
    completado: bool


class RespuestaHistorial(BaseModel):
    historial: list[RegistroDescanso]  # el más reciente primero
    minutos_hoy: float
    cantidad_hoy: int


class RespuestaPuertos(BaseModel):
    detectados: list[str]  # los que podrían ser el BITalino
    todos: list[str]  # todos los puertos serie
