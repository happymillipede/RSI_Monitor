// Ajustes: parámetros de la detección de fatiga y duración del descanso.
// - Los valores por defecto son los de Código_Bitalino_Python.py (se muestran como "Original").
// - Lo que se cambia aquí se guarda en datos/config.json; el original no se toca nunca.
// - "Restaurar valores por defecto" vuelve a usar los del código (y 10 min de descanso).
// - Los parámetros de detección se usan desde el próximo Encender; el descanso, al instante.
// Los umbrales se muestran en % (el original los guarda como fracción: 0.20 = 20 %).
// Qué se puede editar aquí: los textos de ETIQUETAS.

"use client";

import { useState } from "react";
import * as api from "@/lib/api";
import type { ParametroConfig, RespuestaConfig } from "@/lib/tipos";
import estilos from "./Ajustes.module.css";

const ETIQUETAS: Record<string, string> = {
  RMS_INCREASE_THRESHOLD: "Aumento de RMS sobre la línea base",
  MDF_DECREASE_THRESHOLD: "Baja de MDF bajo la línea base",
  ALERT_PERSISTENCE_S: "Tiempo que debe durar el patrón para alertar",
  BASELINE_DURATION_S: "Duración de la línea base",
  TREND_INTERVAL_S: "Intervalo de tendencia",
};
const EN_PORCENTAJE = new Set(["RMS_INCREASE_THRESHOLD", "MDF_DECREASE_THRESHOLD"]);
const CIFRAS = 6; // para mostrar 15 y no 15.000000000000002

const mostrar = (n: number) => String(Number(n.toPrecision(CIFRAS)));
const unidad = (nombre: string) => (EN_PORCENTAJE.has(nombre) ? "%" : "s");
const aPantalla = (nombre: string, valor: number) => (EN_PORCENTAJE.has(nombre) ? valor * 100 : valor);
const aConfig = (nombre: string, valor: number) => (EN_PORCENTAJE.has(nombre) ? valor / 100 : valor);

function valoresIniciales(config: RespuestaConfig): Record<string, string> {
  const valores: Record<string, string> = { duracion: mostrar(config.duracion_fatiga_min) };
  for (const p of config.parametros) {
    valores[p.nombre] = mostrar(aPantalla(p.nombre, p.valor));
  }
  return valores;
}

interface Props {
  config: RespuestaConfig;
  alGuardar: (config: RespuestaConfig) => void;
  alError: (mensaje: string) => void;
}

export default function Ajustes({ config, alGuardar, alError }: Props) {
  const [valores, setValores] = useState(() => valoresIniciales(config));
  const [guardando, setGuardando] = useState(false);
  const [mensaje, setMensaje] = useState("");

  async function guardar(restaurar: boolean) {
    setGuardando(true);
    setMensaje("");
    try {
      const parametros: Record<string, number> = {};
      for (const p of config.parametros) {
        parametros[p.nombre] = aConfig(p.nombre, Number(valores[p.nombre]));
      }
      const nueva = await api.guardarConfig(
        restaurar ? { restaurar: true } : { parametros, duracion_fatiga_min: Number(valores.duracion) },
      );
      setValores(valoresIniciales(nueva));
      alGuardar(nueva);
      setMensaje(restaurar ? "Se restauraron los valores por defecto." : "Ajustes guardados.");
    } catch (e) {
      alError((e as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  return (
    <details className={`tarjeta ${estilos.ajustes}`}>
      <summary>Ajustes</summary>
      <p className={estilos.nota}>
        Los parámetros de la detección se usan desde el próximo Encender. Con los umbrales de prueba (SIM_*)
        marcados, la simulación usa los del original en vez de estos.
      </p>
      {config.parametros.map((p) => (
        <Campo
          key={p.nombre}
          parametro={p}
          valor={valores[p.nombre]}
          alCambiar={(valor) => setValores({ ...valores, [p.nombre]: valor })}
        />
      ))}
      <label className={estilos.campo}>
        <span>Duración del descanso por fatiga</span>
        <span className={estilos.entrada}>
          <input
            type="number"
            min={1}
            value={valores.duracion}
            onChange={(e) => setValores({ ...valores, duracion: e.target.value })}
          />{" "}
          min
        </span>
      </label>
      <div className={estilos.botones}>
        <button onClick={() => guardar(false)} disabled={guardando}>
          Guardar
        </button>
        <button onClick={() => guardar(true)} disabled={guardando}>
          Restaurar valores por defecto
        </button>
      </div>
      {mensaje && <p className={estilos.nota}>{mensaje}</p>}
    </details>
  );
}

function Campo(props: { parametro: ParametroConfig; valor: string; alCambiar: (valor: string) => void }) {
  const { nombre, original, personalizado, minimo, maximo } = props.parametro;
  return (
    <label className={estilos.campo}>
      <span>
        {ETIQUETAS[nombre] ?? nombre}
        {personalizado && <strong className={estilos.cambiado}> (cambiado)</strong>}
        <small className={estilos.original}>
          {nombre} · original: {mostrar(aPantalla(nombre, original))} {unidad(nombre)}
        </small>
      </span>
      <span className={estilos.entrada}>
        <input
          type="number"
          step="any"
          min={aPantalla(nombre, minimo)}
          max={aPantalla(nombre, maximo)}
          value={props.valor}
          onChange={(e) => props.alCambiar(e.target.value)}
        />{" "}
        {unidad(nombre)}
      </span>
    </label>
  );
}
