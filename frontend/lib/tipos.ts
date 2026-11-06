// Tipos de los mensajes entre el backend y el frontend.
// Es una copia a mano de backend/app/mensajes.py: si cambian un campo allá, cámbienlo aquí.
// Los números que pueden faltar (NaN en el original) llegan como null.

export type Modo = "real" | "simulacion";
export type Escenario = "normal" | "fatigue_test";
export type EstadoConexion = "Desconectado" | "Buscando" | "Conectando" | "Conectado" | "Error";

// --- Partes que se repiten ---

export interface PuntoTendencia {
  tiempo: number;
  rms: number | null;
  mdf: number | null;
}

export interface Muestra {
  tiempo: number;
  valor: number;
}

export interface Bloque {
  n_medicion: number;
  ultimo_valor_emg: number | null;
  ultimo_rms: number | null;
  ultimo_mdf: number | null;
  muestras_recientes: Muestra[];
  texto_panel: string;
}

export interface LineaBase {
  rms: number;
  mdf: number;
  texto: string;
}

export interface Calibracion {
  calibrando: boolean;
  texto: string;
  linea_base: LineaBase | null;
}

export interface Parametros {
  TREND_INTERVAL_S: number;
  TREND_WINDOW_S: number;
  BASELINE_DURATION_S: number;
  ALERT_PERSISTENCE_S: number;
  RMS_INCREASE_THRESHOLD: number;
  MDF_DECREASE_THRESHOLD: number;
}

export interface InfoConexion {
  estado: EstadoConexion;
  puerto: string | null;
  version: string | null;
  detalle: string;
  en_docker: boolean;
}

export interface InfoMedicion {
  encendida: boolean;
  modo_preferido: Modo;
  modo: Modo | null;
  escenario: Escenario | null;
  velocidad: number | null;
  umbrales_sim: boolean;
  estado: string;
  ruta_csv: string | null;
}

export interface InfoAlerta {
  pendiente: boolean;
  texto: string;
  aclaracion: string;
  minutos: number;
}

export interface InfoDescanso {
  activo: boolean;
  nombre: string | null;
  origen: "fatiga" | "manual" | null;
  duracion_planeada_s: number;
  segundos_restantes: number;
  minutos_hoy: number;
  cantidad_hoy: number;
}

export interface InfoReloj {
  segundos_hoy: number;
  segundos_sesion: number;
  texto_hoy: string;
  texto_sesion: string;
  corriendo: boolean;
}

// --- Mensajes del WebSocket ---

export interface MensajeEstado {
  tipo: "estado";
  estado_app: string;
  medicion: InfoMedicion;
  conexion: InfoConexion;
  parametros: Parametros;
  calibracion: Calibracion;
  tendencia: PuntoTendencia[];
  ultimo_bloque: Bloque | null;
  alerta: InfoAlerta;
  descanso: InfoDescanso;
  reloj: InfoReloj;
}

export interface MensajeConexion {
  tipo: "conexion";
  estado_app: string;
  medicion: InfoMedicion;
  conexion: InfoConexion;
}

export interface MensajeBloque {
  tipo: "bloque";
  bloque: Bloque;
}

export interface MensajeTendencia {
  tipo: "tendencia";
  estado_app: string;
  punto: PuntoTendencia;
  calibracion: Calibracion;
}

export interface MensajeAlerta {
  tipo: "alerta";
  estado_app: string;
  alerta: InfoAlerta;
}

export interface MensajeDescanso {
  tipo: "descanso";
  estado_app: string;
  evento: "iniciado" | "terminado";
  completado: boolean;
  descanso: InfoDescanso;
}

export interface MensajeReloj {
  tipo: "reloj";
  reloj: InfoReloj;
  segundos_restantes_descanso: number;
}

export type MensajeServidor =
  | MensajeEstado
  | MensajeConexion
  | MensajeBloque
  | MensajeTendencia
  | MensajeAlerta
  | MensajeDescanso
  | MensajeReloj;

// --- Pedidos a la API REST ---

export interface PedidoEncender {
  modo: Modo;
  escenario?: Escenario;
  velocidad?: number;
  umbrales_sim?: boolean;
}

export interface PedidoDescanso {
  plantilla?: number;
  minutos?: number;
}

export interface Plantilla {
  nombre: string;
  duracion_min: number;
}

export interface PedidoConfig {
  parametros?: Record<string, number | null>;
  duracion_fatiga_min?: number;
  usar_umbrales_sim?: boolean;
  restaurar?: boolean;
}

export interface PedidoReconectar {
  puerto: string | null;
}

// --- Respuestas de la API REST ---

export interface ParametroConfig {
  nombre: string;
  valor: number;
  original: number;
  sim: number;
  personalizado: boolean;
  minimo: number;
  maximo: number;
}

export interface RespuestaConfig {
  parametros: ParametroConfig[];
  duracion_fatiga_min: number;
  usar_umbrales_sim: boolean;
  velocidades: number[];
  TREND_WINDOW_S: number;
}

export interface RespuestaPlantillas {
  plantillas: Plantilla[];
}

export interface RegistroDescanso {
  nombre: string;
  origen: "fatiga" | "manual";
  inicio: string;
  fin: string;
  duracion_planeada_min: number;
  duracion_real_min: number;
  completado: boolean;
}

export interface RespuestaHistorial {
  historial: RegistroDescanso[];
  minutos_hoy: number;
  cantidad_hoy: number;
}

export interface RespuestaPuertos {
  detectados: string[];
  todos: string[];
}
