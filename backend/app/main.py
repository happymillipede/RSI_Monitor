"""
Punto de entrada de RSI Monitor: servidor web (FastAPI + Uvicorn). Se ejecuta desde backend/.

    python -m app.main                    servidor en http://127.0.0.1:8000
    python -m app.main --sim              ídem, con el botón Encender en modo simulación
    python -m app.main --host 0.0.0.0     para Docker (el puerto se publica solo en 127.0.0.1)
    python -m app.main --sim --headless --velocidad 10
                                          sin navegador: imprime las alertas (ver sin_navegador.py)

Rutas:
- /api/...  acciones (REST). La lista completa está en el README.
- /ws       tiempo real (WebSocket): mensajes JSON con un campo "tipo" (ver mensajes.py).
- /         el frontend compilado (backend/estaticos/), si existe.

Las rutas son "async def" a propósito: así corren en el bucle de asyncio, el mismo
que recibe los avisos del hilo de medición, y nunca se pisan.

Seguridad: el servidor escucha solo en 127.0.0.1. Además, los POST/PUT/DELETE y el
WebSocket revisan el encabezado Origin, para que otra página web abierta en el
navegador no pueda manejar la app.

Qué se puede editar aquí: las rutas. El puerto, el host y el origen de desarrollo
están en config.json (sección "servidor").
"""

import argparse
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import almacenamiento, mensajes
from app.servicio import ErrorServicio, crear_servicio

METODOS_SIN_CAMBIOS = {"GET", "HEAD", "OPTIONS"}
CODIGO_ORIGEN_NO_PERMITIDO = 1008  # código de cierre del WebSocket ("violación de política")
CODIGO_INTENTAR_DE_NUEVO = 1013  # código de cierre del WebSocket ("inténtelo más tarde")

PAGINA_SIN_FRONTEND = """<!doctype html><html lang="es"><meta charset="utf-8"><title>RSI Monitor</title>
<body style="font-family:sans-serif;max-width:40em;margin:3em auto">
<h1>RSI Monitor</h1><p>El backend está funcionando, pero falta compilar el frontend.</p>
<p>Ejecuten <code>python compilar.py</code> en la carpeta del proyecto, o abran el frontend de
desarrollo con <code>npm run dev</code> en <code>frontend/</code>.</p></body></html>"""


def leer_argumentos(argumentos=None):
    lector = argparse.ArgumentParser(description="RSI Monitor: detector de fatiga muscular con BITalino.")
    lector.add_argument("--sim", action="store_true", help="usar el BITalino simulado")
    lector.add_argument("--host", default=None, help="dirección donde escucha el servidor (por defecto, la de config.json)")
    lector.add_argument("--puerto", type=int, default=None, help="puerto del servidor (por defecto, el de config.json)")
    lector.add_argument("--headless", action="store_true", help="medir sin navegador e imprimir las alertas")
    lector.add_argument("--velocidad", type=float, default=None, help="velocidad de la simulación (1, 10; 0 = sin esperar)")
    lector.add_argument("--escenario", choices=["normal", "fatigue_test"], default=None)
    lector.add_argument("--umbrales-sim", action="store_true", help="usar los umbrales SIM_* del original")
    lector.add_argument("--duracion", type=float, default=None, help="segundos de señal a medir (modo sin navegador)")
    lector.add_argument("--detalle", action="store_true", help="imprimir cada intervalo (modo sin navegador)")
    return lector.parse_args(argumentos)


def origenes_permitidos(servicio, puerto):
    """La página servida por este mismo servidor y el frontend de desarrollo (next dev)."""
    propios = {f"http://127.0.0.1:{puerto}", f"http://localhost:{puerto}"}
    return propios | set(servicio.configuracion["servidor"]["origenes_desarrollo"])


def crear_app(servicio, puerto):
    permitidos = origenes_permitidos(servicio, puerto)

    def origen_permitido(origen):
        # Sin Origin = no es una página web (ej. curl o las pruebas): se permite.
        return origen is None or origen in permitidos

    @asynccontextmanager
    async def ciclo_de_vida(app):
        servicio.iniciar(asyncio.get_running_loop())
        tarea = asyncio.create_task(servicio.tarea_cada_segundo())
        yield
        tarea.cancel()
        servicio.cerrar()

    app = FastAPI(title="RSI Monitor", lifespan=ciclo_de_vida)
    app.state.servicio = servicio
    app.add_middleware(
        CORSMiddleware,
        allow_origins=servicio.configuracion["servidor"]["origenes_desarrollo"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def revisar_origen(request: Request, siguiente):
        if request.method not in METODOS_SIN_CAMBIOS and not origen_permitido(request.headers.get("origin")):
            return JSONResponse({"detail": "Origen no permitido."}, status_code=403)
        return await siguiente(request)

    # Errores -> respuestas con un mensaje en palabras simples ("detail")
    @app.exception_handler(ErrorServicio)
    async def error_servicio(request, error):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(ValueError)
    async def error_valor(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.exception_handler(IndexError)
    async def error_indice(request, error):
        return JSONResponse({"detail": str(error)}, status_code=404)

    # --- Estado y medición ---

    @app.get("/api/estado", response_model=mensajes.MensajeEstado)
    async def estado():
        return servicio.foto()

    @app.post("/api/medicion/encender", response_model=mensajes.MensajeEstado)
    async def encender(pedido: mensajes.PedidoEncender):
        servicio.encender(pedido)
        return servicio.foto()

    @app.post("/api/medicion/apagar", response_model=mensajes.MensajeEstado)
    async def apagar():
        servicio.apagar()
        return servicio.foto()

    # --- Conexión ---

    @app.get("/api/puertos", response_model=mensajes.RespuestaPuertos)
    async def puertos():
        return servicio.puertos()

    @app.post("/api/conexion/reconectar", response_model=mensajes.MensajeEstado)
    async def reconectar(pedido: mensajes.PedidoReconectar):
        servicio.reconectar(pedido)
        return servicio.foto()

    # --- Configuración ---

    @app.get("/api/config", response_model=mensajes.RespuestaConfig)
    async def leer_config():
        return servicio.respuesta_config()

    @app.put("/api/config", response_model=mensajes.RespuestaConfig)
    async def guardar_config(pedido: mensajes.PedidoConfig):
        return servicio.guardar_config(pedido)

    # --- Alerta y descansos ---

    @app.post("/api/alerta/aceptar", response_model=mensajes.MensajeEstado)
    async def aceptar_alerta():
        servicio.aceptar_alerta()
        return servicio.foto()

    @app.post("/api/descanso/iniciar", response_model=mensajes.MensajeEstado)
    async def iniciar_descanso(pedido: mensajes.PedidoDescanso):
        servicio.iniciar_descanso(pedido)
        return servicio.foto()

    @app.post("/api/descanso/terminar", response_model=mensajes.MensajeEstado)
    async def terminar_descanso():
        servicio.terminar_descanso(completado=False)
        return servicio.foto()

    @app.get("/api/descansos/historial", response_model=mensajes.RespuestaHistorial)
    async def historial():
        return servicio.historial()

    @app.get("/api/plantillas", response_model=mensajes.RespuestaPlantillas)
    async def listar_plantillas():
        return servicio.respuesta_plantillas()

    @app.post("/api/plantillas", response_model=mensajes.RespuestaPlantillas)
    async def crear_plantilla(plantilla: mensajes.Plantilla):
        return servicio.crear_plantilla(plantilla)

    @app.put("/api/plantillas/{indice}", response_model=mensajes.RespuestaPlantillas)
    async def editar_plantilla(indice: int, plantilla: mensajes.Plantilla):
        return servicio.editar_plantilla(indice, plantilla)

    @app.delete("/api/plantillas/{indice}", response_model=mensajes.RespuestaPlantillas)
    async def borrar_plantilla(indice: int):
        return servicio.borrar_plantilla(indice)

    # --- Tiempo real ---

    @app.websocket("/ws")
    async def tiempo_real(websocket: WebSocket):
        if not origen_permitido(websocket.headers.get("origin")):
            await websocket.close(code=CODIGO_ORIGEN_NO_PERMITIDO)
            return
        await websocket.accept()
        # La foto y el registro van juntos (sin await entre medio): así no se pierde ni se repite nada.
        foto = servicio.foto().model_dump_json()
        cola = servicio.agregar_cliente()
        try:
            await websocket.send_text(foto)
            while (texto := await cola.get()) is not None:
                await websocket.send_text(texto)
            await websocket.close(code=CODIGO_INTENTAR_DE_NUEVO)  # el navegador se atrasó
        except (WebSocketDisconnect, RuntimeError):
            pass  # el navegador cerró la pestaña o se recargó
        finally:
            servicio.quitar_cliente(cola)

    # --- Frontend compilado (va al final para no tapar /api ni /ws) ---

    if (almacenamiento.CARPETA_ESTATICOS / "index.html").exists():
        app.mount("/", StaticFiles(directory=almacenamiento.CARPETA_ESTATICOS, html=True), name="frontend")
    else:

        @app.get("/", response_class=HTMLResponse)
        async def sin_frontend():
            return PAGINA_SIN_FRONTEND

    return app


def principal(argumentos=None):
    argumentos = leer_argumentos(argumentos)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        servicio = crear_servicio(modo_preferido="simulacion" if argumentos.sim else "real")
    except Exception as error:
        print(f"No se pudo iniciar RSI Monitor:\n{error}")
        return 1

    if argumentos.headless:
        from app.sin_navegador import ejecutar_sin_navegador

        return ejecutar_sin_navegador(argumentos, servicio.original, servicio.configuracion, servicio.carpeta_datos)

    ajustes = servicio.configuracion["servidor"]
    host = argumentos.host or ajustes["host"]
    puerto = argumentos.puerto or ajustes["puerto"]
    print(f"RSI Monitor en http://localhost:{puerto}  (Ctrl+C para detener)")
    uvicorn.run(crear_app(servicio, puerto), host=host, port=puerto, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
