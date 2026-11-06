// Panel de conexión con el BITalino (siempre visible).
// Muestra el estado (Desconectado / Buscando / Conectando / Conectado / Error), el
// último mensaje en palabras simples, el puerto y la versión del BITalino.
// Si el backend corre en Docker, avisa que solo se puede usar la simulación.
// Qué se puede editar aquí: los textos y los colores de cada estado.

"use client";

import type { EstadoConexion, InfoConexion } from "@/lib/tipos";
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
  simulacion: boolean;
}

export default function PanelConexion({ conexion, simulacion }: Props) {
  const conectado = conexion.estado === "Conectado";
  return (
    <section className="tarjeta">
      <h2>Conexión</h2>
      <p className={estilos.estado}>
        <span className={estilos.punto} style={{ background: COLORES[conexion.estado] }} />
        {conexion.estado}
        {simulacion && conectado && " (simulado)"}
      </p>
      {conectado && conexion.puerto && <p className={estilos.dato}>Puerto: {conexion.puerto}</p>}
      {conectado && conexion.version && <p className={estilos.dato}>Versión: {conexion.version}</p>}
      {conexion.detalle && <p className={estilos.detalle}>{conexion.detalle}</p>}
      {conexion.en_docker && (
        <p className={estilos.docker}>
          El backend corre en Docker: el modo real no está disponible. Solo se puede usar la simulación.
        </p>
      )}
    </section>
  );
}
