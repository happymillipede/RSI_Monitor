// Estructura común de la página: idioma, título de la pestaña, favicon y estilos generales.
// Qué se puede editar aquí: el título y la descripción.
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RSI Monitor",
  description: "Detector de fatiga muscular con BITalino (Grupo 2).",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
