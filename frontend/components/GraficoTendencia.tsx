// Un gráfico de tendencia (RMS o MDF), como los del original.
// Muestra solo los últimos TREND_WINDOW_S segundos: la ventana se desplaza igual que
// en el original (extremo derecho = max(TREND_WINDOW_S, último tiempo)).
// Qué se puede editar aquí: alto del gráfico, grosor de la línea y tamaño de los puntos.

"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PuntoTendencia } from "@/lib/tipos";

const ALTO_PX = 230;
const GROSOR_LINEA = 2;
const RADIO_PUNTO = 2.5;
const DECIMALES = 3;
const LETRA_EJES_PX = 12;

interface Props {
  titulo: string;
  etiquetaY: string;
  campo: "rms" | "mdf";
  color: string;
  puntos: PuntoTendencia[];
  ventanaS: number;
}

export default function GraficoTendencia({ titulo, etiquetaY, campo, color, puntos, ventanaS }: Props) {
  // Igual que las líneas 307-310 del original.
  const ultimo = puntos.length ? puntos[puntos.length - 1].tiempo : 0;
  const derecho = Math.max(ventanaS, ultimo);
  const izquierdo = derecho - ventanaS;
  const visibles = puntos.filter((punto) => punto.tiempo >= izquierdo);

  return (
    <figure style={{ margin: 0 }}>
      <figcaption style={{ fontWeight: 600, marginBottom: 4 }}>{titulo}</figcaption>
      <ResponsiveContainer width="100%" height={ALTO_PX}>
        <LineChart data={visibles} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="tiempo"
            type="number"
            domain={[izquierdo, derecho]}
            allowDataOverflow
            tickFormatter={(valor: number) => valor.toFixed(0)}
            fontSize={LETRA_EJES_PX}
            label={{ value: "Tiempo (s)", position: "insideBottom", offset: -4 }}
          />
          <YAxis
            domain={["auto", "auto"]}
            width={64}
            tickFormatter={(valor: number) => valor.toFixed(1)}
            fontSize={LETRA_EJES_PX}
            label={{ value: etiquetaY, angle: -90, position: "insideLeft", style: { textAnchor: "middle", fontSize: LETRA_EJES_PX } }}
          />
          <Tooltip
            formatter={(valor) => (typeof valor === "number" ? valor.toFixed(DECIMALES) : String(valor))}
            labelFormatter={(valor) => `t = ${Number(valor).toFixed(1)} s`}
          />
          <Line
            dataKey={campo}
            name={etiquetaY}
            stroke={color}
            strokeWidth={GROSOR_LINEA}
            dot={{ r: RADIO_PUNTO, fill: color }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </figure>
  );
}
