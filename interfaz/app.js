"use strict";

// Lógica de la ventana principal. Python calcula todo; aquí solo se muestran los datos
// y se llaman los métodos de Python con window.pywebview.api.<método>().
// Python envía las novedades con window.rsi.recibir(mensaje) (ver app.py).
// Qué se puede editar aquí: los textos, los colores de los gráficos y las ventanas de tiempo.

(() => {
    const $ = id => document.getElementById(id);
    const api = () => window.pywebview.api;

    const COLORES = { rms: "#e67e22", mdf: "#2ca02c", fatiga: "#c0392b", crudo: "#2e86c1", rmsBloque: "#c0392b", mdfBloque: "#8e44ad" };
    const VENTANAS_TENDENCIA = [[30, "30 s"], [300, "5 min"], [1800, "30 min"], [0, "Todo"]];
    const TEXTO_MUNECO = {
        apagado: "Conecta el dispositivo para empezar.",
        listo: "Listo. Aprieta Comenzar cuando quieras.",
        tranquilo: "Todo bien. ¡Sigue así!",
        cansado: "Tu músculo muestra signos de fatiga.",
        alerta: "Se sugiere tomar un descanso.",
    };

    let estado = null;           // la foto completa que manda Python
    let ventanaTendencias = 30;  // segundos visibles en la pestaña Principal
    let dibujoPendiente = false;

    // ----- Mensajes de Python -----

    window.rsi = {
        recibir(mensaje) {
            if (mensaje.tipo === "estado") {
                estado = mensaje;
            } else if (!estado) {
                return;
            } else if (mensaje.tipo === "bloque") {
                recibirBloque(mensaje);
            } else if (mensaje.tipo === "tendencia") {
                estado.tendencias.push(mensaje.punto);
            } else if (mensaje.tipo === "alerta") {
                estado.alerta = mensaje.alerta;
            } else if (mensaje.tipo === "mensaje") {
                estado.mensajes.push(mensaje.texto);
            }
            mostrar();
        },
    };

    function recibirBloque(mensaje) {
        const p = estado.parametros;
        estado.bloques.push(mensaje.bloque);
        recortar(estado.bloques, p.ventana_bloques_s * 2);
        estado.crudo.push(...mensaje.crudo);
        recortar(estado.crudo, p.ventana_cruda_s);
        estado.grabacion.tiempo_s = mensaje.tiempo_s;
        estado.panel = mensaje.panel;
        estado.alerta = mensaje.alerta;
    }

    // Deja solo los últimos 'segundos' de una lista de [tiempo, ...].
    function recortar(lista, segundos) {
        if (!lista.length) return;
        const desde = lista[lista.length - 1][0] - segundos;
        let quitar = 0;
        while (quitar < lista.length && lista[quitar][0] < desde) quitar++;
        if (quitar) lista.splice(0, quitar);
    }

    // ----- Mostrar el estado -----

    function mostrar() {
        if (!estado) return;
        mostrarBarra();
        mostrarResumen();
        mostrarMuneco();
        mostrarDetalles();
        solicitarDibujo();
    }

    function mostrarBarra() {
        const { conexion, tarea, grabacion, alerta } = estado;
        const conectado = conexion.estado === "Conectado";
        $("estado-conexion").dataset.estado = conexion.estado;
        $("estado-conexion-texto").textContent = conexion.estado === "Conectado" && conexion.puerto
            ? `Conectado · ${conexion.puerto}` : conexion.estado;
        $("simulacion").hidden = !conexion.simulado;
        $("btn-conectar").disabled = Boolean(tarea) && tarea !== "conectando";

        const enCurso = Boolean(tarea);
        const boton = $("btn-comenzar");
        boton.textContent = enCurso ? "Detener" : "Comenzar";
        boton.classList.toggle("peligro", enCurso);
        boton.disabled = !enCurso && !(conectado && estado.calibracion.estado !== "pendiente"
            && ["PASS", "WARN"].includes(estado.calibracion.estado));
        boton.title = boton.disabled ? "Primero conecta y calibra." : "";

        $("banner-alerta").hidden = !alerta.pendiente;
        const aviso = grabacion.mensaje && !grabacion.activa ? grabacion.mensaje : "";
        mostrarAviso(conexion.estado === "Error" ? conexion.detalle : aviso);
        document.title = alerta.pendiente ? "⚠ Riesgo de fatiga — RSI Monitor" : "RSI Monitor";
    }

    function mostrarAviso(texto) {
        $("aviso").hidden = !texto;
        $("aviso").textContent = texto;
    }

    function mostrarResumen() {
        const { calibracion, tarea, alerta, grabacion, parametros } = estado;
        $("tiempo").textContent = formatoReloj(grabacion.tiempo_s);
        const ultimo = ultimoValor(estado.tendencias, 3);
        $("fatiga-actual").textContent = ultimo === null ? "—" : `${ultimo.toFixed(1)} %`;
        if (document.activeElement !== $("umbral")) $("umbral").value = alerta.umbral;
        $("subtitulo-rms").textContent = `Promedio cada ${parametros.intervalo_s} s`;
        $("subtitulo-mdf").textContent = `Mediana Active cada ${parametros.intervalo_s} s`;

        const calibrando = tarea === "calibrando";
        $("btn-calibrar").disabled = estado.conexion.estado !== "Conectado" || Boolean(tarea);
        $("calibracion-progreso").hidden = !calibrando;
        $("calibracion-progreso").value = calibracion.progreso;
        $("calibracion-texto").textContent = textoCalibracion(calibracion, calibrando, parametros.reposo_s);
        $("calibracion-texto").dataset.estado = calibracion.estado;
    }

    function textoCalibracion(calibracion, calibrando, segundos) {
        if (calibrando) return `Calibrando: mantén el músculo en reposo durante ${segundos} s…`;
        if (calibracion.estado === "PASS") return "Calibración OK (PASS).";
        if (calibracion.estado === "WARN") {
            return `Calibración con avisos: ${(calibracion.motivos || []).join("; ")}. `
                + "El índice de fatiga quedará suprimido; conviene volver a calibrar.";
        }
        if (calibracion.estado === "error") return calibracion.lineas.join(" ");
        if (estado.conexion.estado !== "Conectado") return "Conecta el dispositivo y aprieta Calibrar.";
        return `Aprieta Calibrar y mantén el músculo en reposo ${segundos} s.`;
    }

    function mostrarMuneco() {
        const { alerta, conexion, grabacion } = estado;
        const fatiga = ultimoValor(estado.tendencias, 3);
        let animo = "apagado";
        if (alerta.pendiente) animo = "alerta";
        else if (grabacion.activa && fatiga !== null && fatiga >= alerta.umbral / 2) animo = "cansado";
        else if (grabacion.activa) animo = "tranquilo";
        else if (conexion.estado === "Conectado") animo = "listo";
        $("muneco").dataset.animo = animo;
        $("muneco-texto").textContent = TEXTO_MUNECO[animo];
    }

    function mostrarDetalles() {
        const { grabacion, calibracion, tarea } = estado;
        $("panel").textContent = estado.panel || "Esperando datos del BITalino...";
        $("calibracion-lineas").textContent = calibracion.lineas.length ? calibracion.lineas.join("\n") : "Todavía no se calibra.";
        $("mvc-valor").textContent = estado.mvc_rms === null ? "sin calibrar" : `${estado.mvc_rms.toFixed(3)} ADC`;
        const conectado = estado.conexion.estado === "Conectado";
        $("btn-mvc").disabled = !conectado || Boolean(tarea);
        $("btn-mvc").textContent = tarea === "mvc" ? "Calibrando MVC…" : "Calibrar MVC";
        $("btn-borrar-mvc").disabled = estado.mvc_rms === null || Boolean(tarea);
        $("carpeta-datos").textContent = estado.carpeta_datos;
        const lista = $("archivos");
        lista.replaceChildren(...(grabacion.archivos.length ? grabacion.archivos : ["Todavía no hay grabaciones en esta sesión."])
            .map(texto => Object.assign(document.createElement("li"), { textContent: texto })));
        const mensajes = $("mensajes");
        const abajo = mensajes.scrollTop + mensajes.clientHeight >= mensajes.scrollHeight - 4;
        mensajes.textContent = estado.mensajes.join("\n");
        if (abajo) mensajes.scrollTop = mensajes.scrollHeight;
    }

    // ----- Gráficos -----

    function solicitarDibujo() {
        if (!dibujoPendiente) {
            dibujoPendiente = true;
            window.requestAnimationFrame(dibujar);
        }
    }

    function dibujar() {
        dibujoPendiente = false;
        if (!estado) return;
        const p = estado.parametros;
        const serie = (lista, columna) => lista.map(fila => [fila[0], fila[columna]]);
        const ventana = ventanaTendencias || null;
        if (!$("principal").hidden) {
            window.dibujarGrafico($("g-rms"), serie(estado.tendencias, 1), { color: COLORES.rms, ventana, unidad: "ADC", vacio: "Esperando el primer intervalo…" });
            window.dibujarGrafico($("g-fatiga"), serie(estado.tendencias, 3), {
                color: COLORES.fatiga, ventana, unidad: "%", rango: [0, 100], lineaUmbral: estado.alerta.umbral,
                vacio: estado.grabacion.activa ? "Calculando línea base (bloques Active)…" : "Esperando datos…",
            });
        } else {
            window.dibujarGrafico($("g-crudo"), estado.crudo, { color: COLORES.crudo, ventana: p.ventana_cruda_s, unidad: "ADC", conPuntos: false });
            window.dibujarGrafico($("g-rms-bloque"), serie(estado.bloques, 1), { color: COLORES.rmsBloque, ventana: p.ventana_bloques_s, unidad: "ADC" });
            window.dibujarGrafico($("g-mdf-bloque"), serie(estado.bloques, 2), { color: COLORES.mdfBloque, ventana: p.ventana_bloques_s, unidad: "Hz" });
            window.dibujarGrafico($("g-mdf"), serie(estado.tendencias, 2), { color: COLORES.mdf, ventana: p.ventana_tendencia_s, unidad: "Hz" });
        }
    }

    // ----- Utilidades -----

    function ultimoValor(lista, columna) {
        for (let i = lista.length - 1; i >= 0; i--) {
            const valor = lista[i][columna];
            if (typeof valor === "number" && Number.isFinite(valor)) return valor;
        }
        return null;
    }

    function formatoReloj(segundos) {
        const total = Math.floor(segundos || 0);
        const dos = n => String(n).padStart(2, "0");
        return `${dos(Math.floor(total / 3600))}:${dos(Math.floor((total % 3600) / 60))}:${dos(total % 60)}`;
    }

    // Llama a Python y muestra el mensaje si algo no se pudo hacer.
    async function llamar(metodo, ...argumentos) {
        try {
            const respuesta = await api()[metodo](...argumentos);
            if (respuesta && respuesta.ok === false) mostrarAviso(respuesta.mensaje);
            return respuesta;
        } catch (error) {
            mostrarAviso(`Error de comunicación con Python: ${error.message || error}`);
            return null;
        }
    }

    // ----- Ventana de conexión -----

    async function abrirConexion() {
        const sim = estado.simulacion;
        $("modo-sim").value = sim.modo;
        $("velocidad-sim").replaceChildren(...sim.velocidades.map(v =>
            Object.assign(document.createElement("option"), { value: v, textContent: v === 1 ? "×1 (tiempo real)" : `×${v}` })));
        $("velocidad-sim").value = sim.velocidad;
        if (sim.por_defecto || estado.conexion.simulado) document.querySelector('input[value="simulacion"]').checked = true;
        cambiarFuente();
        $("conexion-detalle").textContent = estado.conexion.detalle || "";
        $("dialogo-conexion").showModal();
        await actualizarPuertos();
    }

    async function actualizarPuertos() {
        const respuesta = await llamar("listar_puertos");
        if (!respuesta) return;
        const select = $("puerto");
        const grupo = (titulo, puertos) => {
            const optgroup = Object.assign(document.createElement("optgroup"), { label: titulo });
            optgroup.append(...puertos.map(p => Object.assign(document.createElement("option"), { value: p, textContent: p })));
            return optgroup;
        };
        const otros = respuesta.todos.filter(p => !respuesta.detectados.includes(p));
        select.replaceChildren();
        if (respuesta.detectados.length) select.append(grupo("Podrían ser el BITalino", respuesta.detectados));
        if (otros.length) select.append(grupo("Otros puertos", otros));
        if (!respuesta.todos.length) select.append(Object.assign(document.createElement("option"), { value: "", textContent: "No hay puertos" }));
    }

    function cambiarFuente() {
        const simulacion = document.querySelector('input[name="fuente"]:checked').value === "simulacion";
        $("opciones-bitalino").hidden = simulacion;
        $("opciones-simulacion").hidden = !simulacion;
        $("btn-detectar").hidden = simulacion;
    }

    async function conectar(automatico) {
        const simulacion = document.querySelector('input[name="fuente"]:checked').value === "simulacion";
        const opciones = simulacion
            ? { simulacion: true, modo: $("modo-sim").value, velocidad: Number($("velocidad-sim").value) }
            : { simulacion: false, puerto: automatico ? null : $("puerto").value || null };
        const respuesta = await llamar("conectar", opciones);
        if (respuesta && respuesta.ok) $("dialogo-conexion").close();
    }

    // ----- Botones -----

    function conectarBotones() {
        $("btn-conectar").addEventListener("click", abrirConexion);
        $("btn-actualizar-puertos").addEventListener("click", actualizarPuertos);
        $("btn-conectar-ahora").addEventListener("click", () => conectar(false));
        $("btn-detectar").addEventListener("click", () => conectar(true));
        $("btn-desconectar").addEventListener("click", async () => {
            await llamar("desconectar");
            $("dialogo-conexion").close();
        });
        for (const radio of document.querySelectorAll('input[name="fuente"]')) radio.addEventListener("change", cambiarFuente);
        $("btn-comenzar").addEventListener("click", () => llamar(estado.tarea ? "detener" : "comenzar"));
        $("btn-calibrar").addEventListener("click", () => llamar("calibrar"));
        $("btn-mvc").addEventListener("click", () => llamar("calibrar_mvc"));
        $("btn-borrar-mvc").addEventListener("click", () => llamar("borrar_mvc"));
        $("btn-carpeta").addEventListener("click", () => llamar("abrir_carpeta_datos"));
        $("btn-cerrar-alerta").addEventListener("click", () => llamar("cerrar_alerta"));
        $("umbral").addEventListener("change", async evento => {
            const respuesta = await llamar("cambiar_umbral", evento.target.value);
            if (respuesta && respuesta.ok) mostrarAviso("");
        });
        for (const boton of document.querySelectorAll(".pestana")) {
            boton.addEventListener("click", () => cambiarPestana(boton.dataset.pestana));
        }
        const selector = $("ventana-tendencias");
        selector.append(...VENTANAS_TENDENCIA.map(([segundos, texto]) =>
            Object.assign(document.createElement("option"), { value: segundos, textContent: texto })));
        selector.addEventListener("change", () => {
            ventanaTendencias = Number(selector.value);
            solicitarDibujo();
        });
    }

    function cambiarPestana(nombre) {
        for (const boton of document.querySelectorAll(".pestana")) boton.classList.toggle("activa", boton.dataset.pestana === nombre);
        $("principal").hidden = nombre !== "principal";
        $("detalles").hidden = nombre !== "detalles";
        solicitarDibujo();
    }

    async function iniciar() {
        if (estado) return;
        if (location.hash === "#detalles") cambiarPestana("detalles");
        const foto = await llamar("obtener_estado");
        if (foto) {
            ventanaTendencias = foto.parametros.ventana_tendencia_s;
            $("ventana-tendencias").value = ventanaTendencias;
            window.rsi.recibir(foto);
        }
    }

    conectarBotones();
    new ResizeObserver(solicitarDibujo).observe(document.body);
    window.addEventListener("pywebviewready", iniciar);
    if (window.pywebview && window.pywebview.api) iniciar();
})();
