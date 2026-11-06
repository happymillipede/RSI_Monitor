// Página principal de RSI Monitor.
// - Recibe el estado del backend por el WebSocket y lo guarda con useReducer (lib/reductor.ts).
// - Las acciones (Encender, Aceptar, Tomar descanso...) se envían por la API REST (lib/api.ts).
// - Avisa con notificaciones del sistema cuando llega una alerta o termina un descanso.
// Aquí no se procesa la señal: el backend hace todo y la página solo muestra.
// Qué se puede editar aquí: el orden de los paneles y los textos de las notificaciones.

"use client";

import { useCallback, useEffect, useReducer, useState } from "react";
import Ajustes from "@/components/Ajustes";
import AlertaFatiga from "@/components/AlertaFatiga";
import BotonMedicion from "@/components/BotonMedicion";
import CuentaRegresiva from "@/components/CuentaRegresiva";
import Descansos from "@/components/Descansos";
import Notificaciones from "@/components/Notificaciones";
import PanelConexion from "@/components/PanelConexion";
import PanelTiempoReal from "@/components/PanelTiempoReal";
import RelojUso from "@/components/RelojUso";
import * as api from "@/lib/api";
import { notificar } from "@/lib/notificaciones";
import { reductor } from "@/lib/reductor";
import type { MensajeEstado, MensajeServidor, RespuestaConfig } from "@/lib/tipos";
import { useAvisoPestana } from "@/lib/useAvisoPestana";
import { useWebSocket } from "@/lib/useWebSocket";
import estilos from "./page.module.css";

const TITULO_FIN_DESCANSO = "Terminó el descanso";
const TEXTO_FIN_DESCANSO = "Pueden volver a trabajar. La detección de fatiga vuelve a estar activa.";

// Notificaciones del sistema para los mensajes que las necesitan.
function avisarSiCorresponde(mensaje: MensajeServidor) {
  if (mensaje.tipo === "alerta" && mensaje.alerta.pendiente) {
    notificar(mensaje.alerta.texto, mensaje.alerta.aclaracion, "rsi-alerta", true);
  }
  if (mensaje.tipo === "descanso" && mensaje.evento === "terminado" && mensaje.completado) {
    notificar(TITULO_FIN_DESCANSO, TEXTO_FIN_DESCANSO, "rsi-descanso", false);
  }
}

export default function Pagina() {
  const [estado, despachar] = useReducer(reductor, null);
  const [config, setConfig] = useState<RespuestaConfig | null>(null);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [descansosTerminados, setDescansosTerminados] = useState(0);

  const alRecibir = useCallback((mensaje: MensajeServidor) => {
    despachar({ tipo: "mensaje", mensaje });
    avisarSiCorresponde(mensaje);
    if (mensaje.tipo === "descanso" && mensaje.evento === "terminado") {
      setDescansosTerminados((n) => n + 1); // vuelve a leer el historial
    }
  }, []);
  const conectado = useWebSocket(alRecibir);
  useAvisoPestana(estado?.alerta.pendiente ?? false);

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
        {estado && <RelojUso reloj={estado.reloj} />}
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
            <PanelConexion
              conexion={estado.conexion}
              medicion={estado.medicion}
              ocupado={ocupado}
              alReconectar={(pedido) => ejecutar(() => api.reconectar(pedido))}
              alError={setError}
            />
            <Notificaciones />
            <Ajustes config={config} alGuardar={setConfig} alError={setError} />
          </aside>
          <main className={estilos.principal}>
            {estado.descanso.activo && (
              <CuentaRegresiva
                descanso={estado.descanso}
                ocupado={ocupado}
                alTerminar={() => ejecutar(api.terminarDescanso)}
              />
            )}
            <PanelTiempoReal estado={estado} />
            <Descansos
              bloqueado={estado.alerta.pendiente || estado.descanso.activo}
              ocupado={ocupado}
              actualizacion={descansosTerminados}
              alIniciar={(pedido) => ejecutar(() => api.iniciarDescanso(pedido))}
              alError={setError}
            />
          </main>
        </div>
      ) : (
        <p className={estilos.cargando}>Cargando…</p>
      )}

      {estado?.alerta.pendiente && (
        <AlertaFatiga alerta={estado.alerta} ocupado={ocupado} alAceptar={() => ejecutar(api.aceptarAlerta)} />
      )}
    </div>
  );
}
