// Configuración de Next.js.
// output: "export" crea una página estática (carpeta out/) que después sirve FastAPI,
// así toda la app corre en un solo proceso y un solo puerto.
// Qué se puede editar aquí: casi nada; no agreguen funciones de servidor de Next.js,
// porque la exportación estática no las permite.
import type { NextConfig } from "next";

const configuracion: NextConfig = {
  output: "export",
};

export default configuracion;
