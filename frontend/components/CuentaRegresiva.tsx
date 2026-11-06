// Cuenta regresiva del descanso en curso, con el botón "Terminar antes".
// El tiempo lo lleva el backend, así que sobrevive a una recarga de la página.
// Durante el descanso no se evalúa la fatiga; al terminar, la alerta se rearma.
// Qué se puede editar aquí: los textos.

"use client";

import { formatoReloj } from "@/lib/formato";
import type { InfoDescanso } from "@/lib/tipos";
import estilos from "./CuentaRegresiva.module.css";

interface Props {
  descanso: InfoDescanso;
  ocupado: boolean;
  alTerminar: () => void;
}

export default function CuentaRegresiva({ descanso, ocupado, alTerminar }: Props) {
  const avance = descanso.duracion_planeada_s
    ? 1 - descanso.segundos_restantes / descanso.duracion_planeada_s
    : 1;

  return (
    <section className={`tarjeta ${estilos.caja}`} aria-live="polite">
      <div className={estilos.fila}>
        <div>
          <h2>{descanso.nombre}</h2>
          <p className={estilos.nota}>Durante el descanso no se evalúa la fatiga.</p>
        </div>
        <span className={estilos.tiempo}>{formatoReloj(descanso.segundos_restantes)}</span>
        <button onClick={alTerminar} disabled={ocupado}>
          Terminar antes
        </button>
      </div>
      <div className={estilos.barra}>
        <div className={estilos.relleno} style={{ width: `${Math.min(avance, 1) * 100}%` }} />
      </div>
    </section>
  );
}
