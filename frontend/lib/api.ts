// Llamadas a la API REST del backend (/api/...).
// Cada función devuelve la respuesta ya leída, o lanza un Error con el mensaje del
// backend en palabras simples (campo "detail"), listo para mostrarlo en pantalla.
// Qué se puede editar aquí: agregar una función por cada ruta nueva del backend.

import type {
  MensajeEstado,
  PedidoConfig,
  PedidoDescanso,
  PedidoEncender,
  PedidoReconectar,
  Plantilla,
  RespuestaConfig,
  RespuestaHistorial,
  RespuestaPlantillas,
  RespuestaPuertos,
} from "./tipos";

// Vacío al compilar: la página la sirve el mismo backend. En "npm run dev" sale de .env.development.
export const URL_BACKEND = process.env.NEXT_PUBLIC_URL_BACKEND ?? "";

async function pedir<T>(metodo: string, ruta: string, cuerpo?: unknown): Promise<T> {
  let respuesta: Response;
  try {
    respuesta = await fetch(URL_BACKEND + ruta, {
      method: metodo,
      headers: cuerpo === undefined ? undefined : { "Content-Type": "application/json" },
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
    });
  } catch {
    throw new Error("No se pudo hablar con el backend. ¿Está corriendo?");
  }
  const datos = await respuesta.json().catch(() => null);
  if (!respuesta.ok) {
    const detalle = datos?.detail;
    throw new Error(typeof detalle === "string" ? detalle : `Error ${respuesta.status} del backend.`);
  }
  return datos as T;
}

// --- Medición ---
export const leerEstado = () => pedir<MensajeEstado>("GET", "/api/estado");
export const encender = (pedido: PedidoEncender) => pedir<MensajeEstado>("POST", "/api/medicion/encender", pedido);
export const apagar = () => pedir<MensajeEstado>("POST", "/api/medicion/apagar");

// --- Conexión ---
export const listarPuertos = () => pedir<RespuestaPuertos>("GET", "/api/puertos");
export const reconectar = (pedido: PedidoReconectar) => pedir<MensajeEstado>("POST", "/api/conexion/reconectar", pedido);

// --- Configuración ---
export const leerConfig = () => pedir<RespuestaConfig>("GET", "/api/config");
export const guardarConfig = (pedido: PedidoConfig) => pedir<RespuestaConfig>("PUT", "/api/config", pedido);

// --- Alerta y descansos ---
export const aceptarAlerta = () => pedir<MensajeEstado>("POST", "/api/alerta/aceptar");
export const iniciarDescanso = (pedido: PedidoDescanso) => pedir<MensajeEstado>("POST", "/api/descanso/iniciar", pedido);
export const terminarDescanso = () => pedir<MensajeEstado>("POST", "/api/descanso/terminar");
export const leerHistorial = () => pedir<RespuestaHistorial>("GET", "/api/descansos/historial");

// --- Plantillas ---
export const listarPlantillas = () => pedir<RespuestaPlantillas>("GET", "/api/plantillas");
export const crearPlantilla = (plantilla: Plantilla) => pedir<RespuestaPlantillas>("POST", "/api/plantillas", plantilla);
export const editarPlantilla = (indice: number, plantilla: Plantilla) =>
  pedir<RespuestaPlantillas>("PUT", `/api/plantillas/${indice}`, plantilla);
export const borrarPlantilla = (indice: number) => pedir<RespuestaPlantillas>("DELETE", `/api/plantillas/${indice}`);
