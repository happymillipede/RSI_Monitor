// Cómo cambia lo que se ve en pantalla con cada mensaje del backend (para useReducer).
// "estado" trae la foto completa y la reemplaza; los demás mensajes cambian solo su parte.
// Aquí no se procesa la señal: solo se guardan los datos que manda el backend.
// Qué se puede editar aquí: qué se guarda de cada mensaje.

import type { MensajeEstado, MensajeServidor } from "./tipos";

export type Accion = { tipo: "mensaje"; mensaje: MensajeServidor } | { tipo: "foto"; foto: MensajeEstado };

// null hasta que llega la primera foto.
export type EstadoPantalla = MensajeEstado | null;

export function reductor(estado: EstadoPantalla, accion: Accion): EstadoPantalla {
  if (accion.tipo === "foto") {
    return accion.foto;
  }
  const mensaje = accion.mensaje;
  if (mensaje.tipo === "estado") {
    return mensaje;
  }
  if (estado === null) {
    return null; // todavía no llega la foto: se ignora
  }

  switch (mensaje.tipo) {
    case "conexion":
      return { ...estado, estado_app: mensaje.estado_app, medicion: mensaje.medicion, conexion: mensaje.conexion };
    case "bloque":
      return { ...estado, ultimo_bloque: mensaje.bloque };
    case "tendencia":
      return {
        ...estado,
        estado_app: mensaje.estado_app,
        tendencia: [...estado.tendencia, mensaje.punto],
        calibracion: mensaje.calibracion,
      };
    case "alerta":
      return { ...estado, estado_app: mensaje.estado_app, alerta: mensaje.alerta };
    case "descanso":
      return { ...estado, estado_app: mensaje.estado_app, descanso: mensaje.descanso };
    case "reloj":
      return {
        ...estado,
        reloj: mensaje.reloj,
        descanso: { ...estado.descanso, segundos_restantes: mensaje.segundos_restantes_descanso },
      };
  }
}
