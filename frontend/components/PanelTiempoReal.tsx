// Panel en tiempo real: muestra lo mismo que el código original.
// - Tendencia de RMS y tendencia de MDF (ventana deslizante de TREND_WINDOW_S).
// - Panel de información con los datos de actualizar_panel_adquisicion() (el texto lo arma el backend).
// Además: el indicador de estado de la app, el mensaje de calibración y la línea base.
// Solo aparece midiendo con el BITalino conectado, o en simulación (con el rótulo SIMULACIÓN).
// Qué se puede editar aquí: los textos y los colores de cada estado.

"use client";

import type { MensajeEstado } from "@/lib/tipos";
import GraficoTendencia from "./GraficoTendencia";
import estilos from "./PanelTiempoReal.module.css";

// Mismos colores que el original (matplotlib "tab:orange" y "tab:green")
const COLOR_RMS = "#ff7f0e";
const COLOR_MDF = "#2ca02c";

const TEXTO_ESPERA = "Esperando datos del BITalino..."; // línea 220 del original

// Color del indicador según el estado de la app (los que no están usan el gris).
const COLORES_ESTADO: Record<string, string> = {
  "Calibrando línea base": "var(--azul)",
  Midiendo: "var(--verde)",
  "Riesgo de fatiga: descanso pendiente": "var(--rojo)",
  "En descanso": "var(--turquesa)",
  Conectando: "var(--naranjo)",
  Buscando: "var(--naranjo)",
  Error: "var(--rojo)",
};

interface Props {
  estado: MensajeEstado;
}

export default function PanelTiempoReal({ estado }: Props) {
  const { medicion, conexion, parametros, calibracion } = estado;
  const simulacion = medicion.modo === "simulacion";
  const visible = medicion.encendida && (simulacion || conexion.estado === "Conectado");

  if (!visible) {
    return (
      <section className={`tarjeta ${estilos.vacio}`}>
        <h2>Panel en tiempo real</h2>
        {medicion.encendida ? (
          <p>Esperando la conexión con el BITalino. Revisen el panel de conexión.</p>
        ) : (
          <p>La medición está apagada. Conecten el BITalino (panel de conexión) y aprieten Encender, o usen la simulación.</p>
        )}
      </section>
    );
  }

  return (
    <section className={`tarjeta ${estilos.panel}`}>
      <div className={estilos.cabecera}>
        <span className={estilos.estado} style={{ background: COLORES_ESTADO[estado.estado_app] ?? "var(--gris)" }}>
          {estado.estado_app}
        </span>
        {simulacion && <span className={estilos.simulacion}>SIMULACIÓN</span>}
      </div>

      {calibracion.calibrando && <p className={estilos.calibracion}>{calibracion.texto}</p>}
      {calibracion.linea_base && <p className={estilos.lineaBase}>{calibracion.linea_base.texto}</p>}

      <div className={estilos.contenido}>
        <div className={estilos.graficos}>
          <GraficoTendencia
            titulo={`Tendencia de RMS (promedio cada ${parametros.TREND_INTERVAL_S} s)`}
            etiquetaY="RMS (ADC)"
            campo="rms"
            color={COLOR_RMS}
            puntos={estado.tendencia}
            ventanaS={parametros.TREND_WINDOW_S}
          />
          <GraficoTendencia
            titulo={`Tendencia de MDF (mediana cada ${parametros.TREND_INTERVAL_S} s)`}
            etiquetaY="Frecuencia mediana (Hz)"
            campo="mdf"
            color={COLOR_MDF}
            puntos={estado.tendencia}
            ventanaS={parametros.TREND_WINDOW_S}
          />
        </div>
        <pre className={estilos.informacion}>{estado.ultimo_bloque?.texto_panel ?? TEXTO_ESPERA}</pre>
      </div>
    </section>
  );
}
