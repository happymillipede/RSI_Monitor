// Notificaciones del sistema (Web Notifications API).
// El navegador solo deja mostrarlas si el usuario da permiso: por eso hay un botón
// "Activar notificaciones" (components/Notificaciones.tsx).
// Qué se puede editar aquí: el ícono y las etiquetas.

export type Permiso = NotificationPermission | "no-disponible";

const ICONO = "/favicon-alerta.svg";

export function permisoActual(): Permiso {
  if (typeof window === "undefined" || !("Notification" in window)) {
    return "no-disponible";
  }
  return Notification.permission;
}

export async function pedirPermiso(): Promise<Permiso> {
  if (permisoActual() === "no-disponible") {
    return "no-disponible";
  }
  return Notification.requestPermission();
}

// etiqueta: notificaciones con la misma etiqueta se reemplazan (así varias pestañas no repiten el aviso).
// fija: true = queda en pantalla hasta que el usuario la cierre (requireInteraction).
export function notificar(titulo: string, cuerpo: string, etiqueta: string, fija: boolean) {
  if (permisoActual() !== "granted") {
    return;
  }
  const notificacion = new Notification(titulo, { body: cuerpo, tag: etiqueta, requireInteraction: fija, icon: ICONO });
  notificacion.onclick = () => {
    window.focus();
    notificacion.close();
  };
}
