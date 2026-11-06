// Reglas de estilo del frontend (npm run lint). Usa las reglas recomendadas de Next.js.
// Qué se puede editar aquí: las carpetas que se ignoran.
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([".next/**", "out/**", "next-env.d.ts"]),
]);
