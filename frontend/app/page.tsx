// Página principal de RSI Monitor.
// - Recibe el estado del backend por el WebSocket y lo guarda con useReducer (lib/reductor.ts).
// - Las acciones (Encender, Apagar...) se envían por la API REST (lib/api.ts).
// Aquí no se procesa la señal: el backend hace todo y la página solo muestra.
// Qué se puede editar aquí: el orden de los paneles y los textos generales.

"use client";

import { useCallback, useEffect, useReducer, useState } from "react";
import BotonMedicion from "@/components/BotonMedicion";
import PanelConexion from "@/components/PanelConexion";
import PanelTiempoReal from "@/components/PanelTiempoReal";
import * as api from "@/lib/api";
import { reductor } from "@/lib/reductor";
import type { MensajeEstado, MensajeServidor, RespuestaConfig } from "@/lib/tipos";
import { useWebSocket } from "@/lib/useWebSocket";
import estilos from "./page.module.css";

export default function Pagina() {
  const [estado, despachar] = useReducer(reductor, null);
  const [config, setConfig] = useState<RespuestaConfig | null>(null);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const alRecibir = useCallback((mensaje: MensajeServidor) => despachar({ tipo: "mensaje", mensaje }), []);
  const conectado = useWebSocket(alRecibir);

  useEffect(() => {
    api.leerConfig().then(setConfig, (e: Error) => setError(e.message));
  }, []);

  // Corre una acción de la API: muestra el error si falla y usa la foto que devuelve.
  async function ejecutar(accion: () => Promise<MensajeEstado>) {
    setOcupado(true);
    setError("");
    try {
      despachar({ tipo: "foto", foto: await accion() });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className={estilos.pagina}>
      <header className={estilos.cabecera}>
        <h1>RSI Monitor</h1>
        <span className={estilos.subtitulo}>Detector de fatiga muscular · Grupo 2</span>
      </header>

      {!conectado && <p className={estilos.aviso}>Sin conexión con el backend. Reintentando…</p>}
      {error && (
        <p className={estilos.error} role="alert">
          {error} <button onClick={() => setError("")}>Cerrar</button>
        </p>
      )}

      {estado && config ? (
        <div className={estilos.contenido}>
          <aside className={estilos.lateral}>
            <BotonMedicion
              medicion={estado.medicion}
              enDocker={estado.conexion.en_docker}
              velocidades={config.velocidades}
              umbralesSimGuardado={config.usar_umbrales_sim}
              ocupado={ocupado}
              alEncender={(pedido) => ejecutar(() => api.encender(pedido))}
              alApagar={() => ejecutar(api.apagar)}
            />
            <PanelConexion conexion={estado.conexion} simulacion={estado.medicion.modo === "simulacion"} />
          </aside>
          <main className={estilos.principal}>
            <PanelTiempoReal estado={estado} />
          </main>
        </div>
      ) : (
        <p className={estilos.cargando}>Cargando…</p>
      )}
    </div>
  );
}
