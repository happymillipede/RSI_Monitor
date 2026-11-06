// Formato de números y tiempos para mostrar en pantalla (solo presentación).
// Qué se puede editar aquí: los formatos.

const SEGUNDOS_POR_MINUTO = 60;
const SEGUNDOS_POR_HORA = 3600;

const dosCifras = (n: number) => String(n).padStart(2, "0");

// Ej.: 75 -> "01:15"; 3725 -> "1:02:05". Igual que formato_reloj() del backend.
export function formatoReloj(segundos: number): string {
  const total = Math.max(0, Math.ceil(segundos));
  const horas = Math.floor(total / SEGUNDOS_POR_HORA);
  const minutos = Math.floor((total % SEGUNDOS_POR_HORA) / SEGUNDOS_POR_MINUTO);
  const resto = total % SEGUNDOS_POR_MINUTO;
  return horas ? `${horas}:${dosCifras(minutos)}:${dosCifras(resto)}` : `${dosCifras(minutos)}:${dosCifras(resto)}`;
}

// Ej.: "2026-11-06T10:30:00" -> "10:30"
export function horaDe(fechaIso: string): string {
  return fechaIso.slice(11, 16);
}

// Ej.: 7.5 -> "7,5"
export function minutosTexto(minutos: number): string {
  return minutos.toLocaleString("es", { maximumFractionDigits: 1 });
}
