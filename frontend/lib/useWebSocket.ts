// Hook que mantiene abierta la conexión al WebSocket del backend (/ws).
// - Llama a alRecibir(mensaje) con cada mensaje JSON que llega.
// - Si la conexión se corta (ej. se reinició el backend), vuelve a conectarse sola,
//   con una espera que crece hasta ESPERA_MAXIMA_MS. Al volver, el backend manda
//   primero la foto completa, así que no se pierde nada.
// - Devuelve true mientras está conectado.
// Qué se puede editar aquí: los tiempos de espera.

"use client";

import { useEffect, useRef, useState } from "react";
import { URL_BACKEND } from "./api";
import type { MensajeServidor } from "./tipos";

const ESPERA_INICIAL_MS = 500;
const ESPERA_MAXIMA_MS = 5000;

function direccionWebSocket(): string {
  if (URL_BACKEND) {
    return URL_BACKEND.replace(/^http/, "ws") + "/ws";
  }
  const protocolo = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocolo}//${window.location.host}/ws`;
}

export function useWebSocket(alRecibir: (mensaje: MensajeServidor) => void): boolean {
  const [conectado, setConectado] = useState(false);
  // Se guarda en una referencia para usar siempre la última función sin reconectar.
  const alRecibirRef = useRef(alRecibir);
  useEffect(() => {
    alRecibirRef.current = alRecibir;
  }, [alRecibir]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let temporizador: ReturnType<typeof setTimeout> | undefined;
    let espera = ESPERA_INICIAL_MS;
    let terminado = false;

    function conectar() {
      socket = new WebSocket(direccionWebSocket());
      socket.onopen = () => {
        espera = ESPERA_INICIAL_MS;
        setConectado(true);
      };
      socket.onmessage = (evento) => {
        alRecibirRef.current(JSON.parse(evento.data) as MensajeServidor);
      };
      socket.onclose = () => {
        setConectado(false);
        if (!terminado) {
          temporizador = setTimeout(conectar, espera);
          espera = Math.min(espera * 2, ESPERA_MAXIMA_MS);
        }
      };
    }

    conectar();
    return () => {
      terminado = true;
      clearTimeout(temporizador);
      socket?.close();
    };
  }, []);

  return conectado;
}
