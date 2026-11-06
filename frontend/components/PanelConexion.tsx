// Panel de conexión con el BITalino (siempre visible).
// - Estado: Desconectado / Buscando / Conectando / Conectado / Error, con el último
//   mensaje en palabras simples. Puerto y versión cuando está conectado.
// - Lista de puertos detectados (con botón para actualizarla), un selector y
//   "Reconectar" para probar ese puerto, o "Detectar automáticamente".
// - Si el backend corre en Docker, avisa que solo se puede usar la simulación.
// Qué se puede editar aquí: los textos y los colores de cada estado.

"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import type { EstadoConexion, InfoConexion, InfoMedicion, PedidoReconectar, RespuestaPuertos } from "@/lib/tipos";
import estilos from "./PanelConexion.module.css";

const COLORES: Record<EstadoConexion, string> = {
  Desconectado: "var(--gris)",
  Buscando: "var(--naranjo)",
  Conectando: "var(--naranjo)",
  Conectado: "var(--verde)",
  Error: "var(--rojo)",
};

interface Props {
  conexion: InfoConexion;
  medicion: InfoMedicion;
  ocupado: boolean;
  alReconectar: (pedido: PedidoReconectar) => void;
  alError: (mensaje: string) => void;
}

export default function PanelConexion({ conexion, medicion, ocupado, alReconectar, alError }: Props) {
  const simulacion = medicion.encendida && medicion.modo === "simulacion";
  const conectado = conexion.estado === "Conectado";

  return (
    <section className="tarjeta">
      <h2>Conexión</h2>
      <p className={estilos.estado}>
        <span className={estilos.punto} style={{ background: COLORES[conexion.estado] }} />
        {conexion.estado}
        {simulacion && conectado && " (simulado)"}
      </p>
      {conectado && conexion.puerto && <p className={estilos.dato}>Puerto en uso: {conexion.puerto}</p>}
      {conectado && conexion.version && <p className={estilos.dato}>Versión: {conexion.version}</p>}
      {conexion.detalle && <p className={estilos.detalle}>{conexion.detalle}</p>}

      {conexion.en_docker ? (
        <p className={estilos.docker}>
          El backend corre en Docker: el modo real no está disponible. Solo se puede usar la simulación.
        </p>
      ) : (
        <ElegirPuerto
          conexion={conexion}
          medicion={medicion}
          ocupado={ocupado}
          alReconectar={alReconectar}
          alError={alError}
        />
      )}
    </section>
  );
}

// Por qué no se puede reconectar ahora (o "" si se puede).
function motivoBloqueo(conexion: InfoConexion, medicion: InfoMedicion): string {
  const buscando = conexion.estado === "Buscando" || conexion.estado === "Conectando";
  if (medicion.encendida && medicion.modo === "simulacion") {
    return "En simulación no hay un BITalino que conectar.";
  }
  if (medicion.encendida && conexion.estado === "Conectado") {
    return "Para cambiar de puerto, apaguen la medición.";
  }
  if (!medicion.encendida && buscando) {
    return "Buscando el BITalino…";
  }
  return "";
}

function ElegirPuerto({ conexion, medicion, ocupado, alReconectar, alError }: Props) {
  const [puertos, setPuertos] = useState<RespuestaPuertos>({ detectados: [], todos: [] });
  const [elegido, setElegido] = useState("");

  const actualizar = useCallback(() => {
    api.listarPuertos().then(
      (respuesta) => {
        setPuertos(respuesta);
        setElegido((actual) => actual || respuesta.detectados[0] || respuesta.todos[0] || "");
      },
      (e: Error) => alError(e.message),
    );
  }, [alError]);

  useEffect(actualizar, [actualizar]);

  const bloqueo = motivoBloqueo(conexion, medicion);
  const otros = puertos.todos.filter((puerto) => !puertos.detectados.includes(puerto));

  return (
    <div className={estilos.puertos}>
      <div className={estilos.fila}>
        <select value={elegido} onChange={(e) => setElegido(e.target.value)} aria-label="Puerto del BITalino">
          {puertos.todos.length === 0 && <option value="">No hay puertos</option>}
          {puertos.detectados.length > 0 && (
            <optgroup label="Podrían ser el BITalino">
              {puertos.detectados.map((puerto) => (
                <option key={puerto}>{puerto}</option>
              ))}
            </optgroup>
          )}
          {otros.length > 0 && (
            <optgroup label="Otros puertos">
              {otros.map((puerto) => (
                <option key={puerto}>{puerto}</option>
              ))}
            </optgroup>
          )}
        </select>
        <button onClick={actualizar} title="Volver a buscar los puertos">
          Actualizar
        </button>
      </div>
      <div className={estilos.fila}>
        <button disabled={!elegido || !!bloqueo || ocupado} onClick={() => alReconectar({ puerto: elegido })}>
          Reconectar
        </button>
        <button disabled={!!bloqueo || ocupado} onClick={() => alReconectar({ puerto: null })}>
          Detectar automáticamente
        </button>
      </div>
      {bloqueo && <p className={estilos.detalle}>{bloqueo}</p>}
    </div>
  );
}
