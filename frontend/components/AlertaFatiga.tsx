// Ventana de alerta de fatiga: cubre toda la pantalla y tiene un solo botón, "Aceptar".
// - No se cierra con Escape ni haciendo clic afuera.
// - Aceptar empieza el descanso (lo hace el backend).
// - Si no se acepta, sigue ahí: el estado de la alerta vive en el backend, así que
//   también aparece al recargar la página o en otra pestaña.
// Qué se puede editar aquí: los estilos. El texto viene del backend (app/textos.py).

"use client";

import { useEffect, useRef } from "react";
import type { InfoAlerta } from "@/lib/tipos";
import estilos from "./AlertaFatiga.module.css";

interface Props {
  alerta: InfoAlerta;
  ocupado: boolean;
  alAceptar: () => void;
}

export default function AlertaFatiga({ alerta, ocupado, alAceptar }: Props) {
  const boton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    boton.current?.focus();

    // Escape no cierra la ventana, y Tab no saca el foco del botón.
    function alPresionar(evento: KeyboardEvent) {
      if (evento.key === "Escape" || evento.key === "Tab") {
        evento.preventDefault();
        boton.current?.focus();
      }
    }
    document.addEventListener("keydown", alPresionar, true);
    return () => document.removeEventListener("keydown", alPresionar, true);
  }, []);

  return (
    <div className={estilos.fondo}>
      <div
        className={estilos.ventana}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="titulo-alerta"
        aria-describedby="aclaracion-alerta"
      >
        <div className={estilos.icono} aria-hidden="true">
          ⚠
        </div>
        <h2 id="titulo-alerta" className={estilos.texto}>
          {alerta.texto}
        </h2>
        <p id="aclaracion-alerta" className={estilos.aclaracion}>
          {alerta.aclaracion}
        </p>
        <button ref={boton} className={estilos.aceptar} onClick={alAceptar} disabled={ocupado}>
          Aceptar
        </button>
      </div>
    </div>
  );
}
