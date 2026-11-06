// Reloj de uso del computador: tiempo medido hoy y en la sesión actual.
// Lo lleva el backend: corre solo con la medición encendida y se pausa en los descansos.
// Es solo informativo: no genera recordatorios.
// Qué se puede editar aquí: los textos.

import type { InfoReloj } from "@/lib/tipos";
import estilos from "./RelojUso.module.css";

interface Props {
  reloj: InfoReloj;
}

export default function RelojUso({ reloj }: Props) {
  return (
    <div className={estilos.reloj} title={reloj.corriendo ? "El reloj está corriendo" : "El reloj está en pausa"}>
      <span className={estilos.punto} data-corriendo={reloj.corriendo} />
      <span>
        Uso hoy <strong>{reloj.texto_hoy}</strong>
      </span>
      <span>
        Sesión <strong>{reloj.texto_sesion}</strong>
      </span>
    </div>
  );
}
