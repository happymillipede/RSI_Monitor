// Mientras hay una alerta de fatiga pendiente, la pestaña llama la atención aunque
// esté en segundo plano:
// - el título alterna entre "⚠ Riesgo de fatiga" y el título normal;
// - el favicon cambia al de alerta (rojo).
// Cuando la alerta se acepta, todo vuelve a la normalidad.
// Qué se puede editar aquí: los textos, los íconos y la velocidad del parpadeo.

"use client";

import { useEffect } from "react";

const TITULO_NORMAL = "RSI Monitor";
const TITULO_ALERTA = "⚠ Riesgo de fatiga";
const FAVICON_NORMAL = "/favicon.svg";
const FAVICON_ALERTA = "/favicon-alerta.svg";
const PARPADEO_MS = 1000;

function ponerFavicon(ruta: string) {
  let enlace = document.querySelector<HTMLLinkElement>("link[rel='icon']");
  if (!enlace) {
    enlace = document.createElement("link");
    enlace.rel = "icon";
    document.head.appendChild(enlace);
  }
  enlace.href = ruta;
}

export function useAvisoPestana(alertaPendiente: boolean) {
  useEffect(() => {
    if (!alertaPendiente) {
      document.title = TITULO_NORMAL;
      ponerFavicon(FAVICON_NORMAL);
      return;
    }

    ponerFavicon(FAVICON_ALERTA);
    let mostrarAlerta = true;
    document.title = TITULO_ALERTA;
    const temporizador = setInterval(() => {
      mostrarAlerta = !mostrarAlerta;
      document.title = mostrarAlerta ? TITULO_ALERTA : TITULO_NORMAL;
    }, PARPADEO_MS);

    return () => clearInterval(temporizador);
  }, [alertaPendiente]);
}
