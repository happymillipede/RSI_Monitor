// Botón para activar las notificaciones del sistema, y qué hacer si se negaron.
// La alerta de fatiga y el fin de un descanso se avisan con una notificación, para
// que se vean aunque el navegador esté minimizado.
// Qué se puede editar aquí: los textos.

"use client";

import { useEffect, useState } from "react";
import { pedirPermiso, permisoActual, type Permiso } from "@/lib/notificaciones";
import estilos from "./Notificaciones.module.css";

export default function Notificaciones() {
  // Se lee después de montar, porque al compilar la página no hay "window".
  const [permiso, setPermiso] = useState<Permiso>("default");
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- solo existe en el navegador
    setPermiso(permisoActual());
  }, []);

  if (permiso === "granted") {
    return null;
  }

  return (
    <section className={`tarjeta ${estilos.caja}`}>
      <h2>Notificaciones</h2>
      {permiso === "default" && (
        <>
          <p>Activen las notificaciones para ver la alerta de fatiga aunque el navegador esté minimizado.</p>
          <button onClick={async () => setPermiso(await pedirPermiso())}>Activar notificaciones</button>
        </>
      )}
      {permiso === "denied" && (
        <p>
          Las notificaciones están bloqueadas. Para activarlas, hagan clic en el candado (o el ícono de ajustes) a
          la izquierda de la dirección, permitan las notificaciones y recarguen la página. En macOS y Windows revisen
          también que el navegador tenga permiso en los ajustes de notificaciones del sistema.
        </p>
      )}
      {permiso === "no-disponible" && <p>Este navegador no tiene notificaciones. La alerta igual aparece en la página.</p>}
    </section>
  );
}
