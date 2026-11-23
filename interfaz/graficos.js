"use strict";

// Dibuja un gráfico de líneas en un <canvas>, sin librerías (como BitalinoPywebview).
// puntos: [[tiempo, valor], ...]. Los valores null (NaN en Python) cortan la línea.
// Qué se puede editar aquí: márgenes, colores de la grilla y tamaños de letra.

window.dibujarGrafico = (canvas, puntos, opciones) => {
    const {
        color,
        ventana,                 // segundos visibles (null = todo)
        unidad = "",
        rango = null,            // [mínimo, máximo] fijo, o null para ajustarlo
        conPuntos = true,
        lineaUmbral = null,      // valor de una línea horizontal punteada
        vacio = "Esperando datos…",
    } = opciones;
    const ancho = canvas.clientWidth;
    const alto = canvas.clientHeight;
    if (!ancho || !alto) return;
    const escala = window.devicePixelRatio || 1;
    canvas.width = Math.round(ancho * escala);
    canvas.height = Math.round(alto * escala);
    const ctx = canvas.getContext("2d");
    ctx.scale(escala, escala);

    const margen = { izq: 52, der: 22, sup: 20, inf: 30 };
    const w = ancho - margen.izq - margen.der;
    const h = alto - margen.sup - margen.inf;

    // Ventana deslizante como en el notebook: el extremo derecho es max(ventana, último tiempo).
    const ultimo = puntos.length ? puntos[puntos.length - 1][0] : 0;
    const primero = puntos.length ? puntos[0][0] : 0;
    const anchoVentana = ventana || Math.max(ultimo - primero, 1);
    const derecha = ventana ? Math.max(ventana, ultimo) : Math.max(ultimo, anchoVentana);
    const izquierda = derecha - anchoVentana;
    let inicio = puntos.findIndex(p => p[0] >= izquierda);
    if (inicio < 0) inicio = puntos.length;
    const visibles = puntos.slice(Math.max(0, inicio - 1));
    const valores = visibles.map(p => p[1]).filter(v => typeof v === "number" && Number.isFinite(v));

    let minimo = rango ? rango[0] : (valores.length ? Math.min(...valores) : 0);
    let maximo = rango ? rango[1] : (valores.length ? Math.max(...valores) : 1);
    if (!rango && valores.length) {
        const extra = Math.max((maximo - minimo) * 0.12, Math.abs(maximo) * 0.02, 0.1);
        minimo -= extra;
        maximo += extra;
    }
    const x = t => margen.izq + (t - izquierda) / anchoVentana * w;
    const y = v => margen.sup + h - (v - minimo) / (maximo - minimo) * h;

    const estilo = getComputedStyle(document.documentElement);
    const colorGrilla = estilo.getPropertyValue("--grilla").trim() || "#e8edf3";
    const colorTexto = estilo.getPropertyValue("--texto-suave").trim() || "#64748b";
    ctx.font = '11px system-ui, "Segoe UI", sans-serif';
    ctx.fillStyle = colorTexto;
    ctx.strokeStyle = colorGrilla;
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const t = izquierda + i * anchoVentana / 4;
        const v = minimo + i * (maximo - minimo) / 4;
        ctx.beginPath();
        ctx.moveTo(x(t), margen.sup);
        ctx.lineTo(x(t), margen.sup + h);
        ctx.moveTo(margen.izq, y(v));
        ctx.lineTo(margen.izq + w, y(v));
        ctx.stroke();
        ctx.textAlign = "center";
        ctx.fillText(formatoEje(t, anchoVentana), x(t), alto - 14);
        ctx.textAlign = "right";
        ctx.fillText(v.toFixed(maximo - minimo < 5 ? 2 : 0), margen.izq - 6, y(v) + 4);
    }
    ctx.textAlign = "left";
    ctx.fillText(unidad, 4, 10);
    ctx.textAlign = "center";
    ctx.fillText(tituloEje(anchoVentana, derecha), margen.izq + w / 2, alto - 2);

    ctx.save();
    ctx.beginPath();
    ctx.rect(margen.izq, margen.sup - 3, w + 1, h + 6);
    ctx.clip();
    if (lineaUmbral !== null && lineaUmbral >= minimo && lineaUmbral <= maximo) {
        ctx.strokeStyle = estilo.getPropertyValue("--rojo").trim() || "#c0392b";
        ctx.setLineDash([6, 4]);
        ctx.beginPath();
        ctx.moveTo(margen.izq, y(lineaUmbral));
        ctx.lineTo(margen.izq + w, y(lineaUmbral));
        ctx.stroke();
        ctx.setLineDash([]);
    }
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = conPuntos ? 2 : 1;
    ctx.beginPath();
    let continuar = false;
    for (const [t, v] of visibles) {
        if (typeof v !== "number" || !Number.isFinite(v)) {
            continuar = false;
            continue;
        }
        if (continuar) ctx.lineTo(x(t), y(v));
        else ctx.moveTo(x(t), y(v));
        continuar = true;
    }
    ctx.stroke();
    if (conPuntos) {
        for (const [t, v] of visibles) {
            if (typeof v !== "number" || !Number.isFinite(v)) continue;
            ctx.beginPath();
            ctx.arc(x(t), y(v), 3, 0, 2 * Math.PI);
            ctx.fill();
        }
    }
    ctx.restore();
    if (!valores.length) {
        ctx.fillStyle = colorTexto;
        ctx.textAlign = "center";
        ctx.fillText(vacio, margen.izq + w / 2, margen.sup + h / 2);
    }
};

// Si el gráfico muestra 10 min o más, el eje va en min:s (h:min:s si llega a 1 h).
const SEGUNDOS_EN_MINUTOS = 600;

// En segundos: 75 -> "75". En min:s: 3725 -> "1:02:05".
function formatoEje(segundos, anchoVentana) {
    if (anchoVentana < SEGUNDOS_EN_MINUTOS) return String(+segundos.toFixed(1));
    const total = Math.round(segundos);
    const horas = Math.floor(total / 3600);
    const minutos = Math.floor((total % 3600) / 60);
    const resto = total % 60;
    const dos = n => String(n).padStart(2, "0");
    return horas ? `${horas}:${dos(minutos)}:${dos(resto)}` : `${minutos}:${dos(resto)}`;
}

function tituloEje(anchoVentana, derecha) {
    if (anchoVentana < SEGUNDOS_EN_MINUTOS) return "Tiempo (s)";
    return derecha >= 3600 ? "Tiempo (h:min:s)" : "Tiempo (min:s)";
}
