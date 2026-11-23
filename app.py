"""
RSI Monitor: punto de entrada. Abre la ventana (pywebview) y conecta la interfaz
(carpeta interfaz/: HTML, JavaScript y CSS) con el procesamiento en Python.

    python app.py              abre la app
    python app.py --simular    el botón "Conectar dispositivo" propone la simulación
    python app.py --depurar    abre también las herramientas de desarrollo de la ventana

Cómo se comunican Python y la ventana (igual que en BitalinoPywebview):
- JavaScript llama a los métodos de la clase Api con window.pywebview.api.<método>().
- Python envía cada novedad con window.rsi.recibir(mensaje) (evaluate_js). Los
  mensajes tienen un campo "tipo": estado, bloque, tendencia, alerta.
- La conexión, la calibración y la grabación corren en un hilo aparte, para que la
  ventana nunca se congele. Solo se hace una de esas tareas a la vez.

La alerta de fatiga abre una ventana aparte (interfaz/alerta.html) que queda encima
de todas las demás aplicaciones, como el pop-up de la app anterior.

Qué se puede editar aquí: los tamaños y títulos de las ventanas.
"""

import argparse
import json
import math
import os
import subprocess
import sys
import threading
import traceback
from collections import deque
from pathlib import Path

from calibracion import calibrar_mvc, comprobar_reposo
from conexion import BitalinoConLimite, conectar_automatico, explicar_error, lista_candidatos, puertos_detectados, todos_los_puertos
from configuracion import (
    BLOCK_WINDOW_S,
    CARPETA_DATOS,
    CARPETA_INTERFAZ,
    DURACION_MAXIMA_S,
    FATIGUE_ALERT_THRESHOLD,
    FS,
    NOMBRE_APP,
    PERIODO,
    PUERTO,
    RAW_WINDOW_S,
    REST_CHECK_S,
    TIEMPO_LIMITE_CONEXION_S,
    TREND_INTERVAL_S,
    TREND_WINDOW_S,
    VELOCIDADES_SIMULACION,
    guardar_ajustes,
    leer_ajustes,
)
from fatiga import AnalizadorFatiga, umbral_actividad
from grabacion import archivos_siguientes, grabar, texto_panel
from procesamiento import BITalinoSimulado

TAMANO_VENTANA = (1280, 860)
TAMANO_MINIMO = (920, 640)
TAMANO_ALERTA = (520, 330)
TITULO_ALERTA = "ALERTA — RSI Monitor"
MAXIMO_MENSAJES = 300
MAXIMO_PUNTOS_TENDENCIA = int(DURACION_MAXIMA_S / TREND_INTERVAL_S) + 1
MAXIMO_BLOQUES = int(BLOCK_WINDOW_S) + 1
SEGUNDOS_POR_MINUTO = 60

# Tareas (solo una a la vez)
CONECTANDO = "conectando"
CALIBRANDO = "calibrando"
CALIBRANDO_MVC = "mvc"
GRABANDO = "grabando"


def para_json(valor):
    """JSON estricto: NaN e infinito se envían como null."""
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    if isinstance(valor, dict):
        return {clave: para_json(v) for clave, v in valor.items()}
    if isinstance(valor, (list, tuple, deque)):
        return [para_json(v) for v in valor]
    return valor


def abrir_carpeta(carpeta):
    if sys.platform == "win32":
        os.startfile(carpeta)  # noqa: S606 (abre el Explorador de Windows)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(carpeta)])
    else:
        subprocess.Popen(["xdg-open", str(carpeta)])


class Api:
    """
    Métodos que la interfaz llama con window.pywebview.api.<método>().
    Los atributos que empiezan con "_" no se exponen a JavaScript.
    """

    def __init__(self, carpeta_datos=CARPETA_DATOS, simular=False, abrir_bitalino=BitalinoConLimite, buscar_puertos=puertos_detectados):
        self._carpeta = Path(carpeta_datos)
        self._carpeta.mkdir(parents=True, exist_ok=True)
        self._ajustes = leer_ajustes(carpeta_datos)
        self._simular_por_defecto = simular
        self._abrir_bitalino = abrir_bitalino
        self._buscar_puertos = buscar_puertos
        self._candado = threading.Lock()
        self._hilo = None
        self._tarea = None
        self._detener = threading.Event()
        self._cerrando = threading.Event()
        self._enviar_js = None  # función que ejecuta JavaScript en la ventana
        self._crear_popup = None  # función que abre el pop-up de alerta
        self._cerrar_popup = None

        self._dispositivo = None
        self._conexion = {"estado": "Desconectado", "detalle": "", "puerto": None, "version": None, "simulado": False}
        self._reposo = None
        self._calibracion = {"estado": "pendiente", "progreso": 0.0, "lineas": []}
        self._mvc = None
        self._analizador = None
        self._grabacion = {"id": 0, "activa": False, "tiempo_s": 0.0, "archivos": [], "mensaje": ""}
        self._alerta = {"pendiente": False, "indice": None, "tiempo_s": None}
        self._tendencias = deque(maxlen=MAXIMO_PUNTOS_TENDENCIA)
        self._bloques = deque(maxlen=MAXIMO_BLOQUES)
        self._crudo = deque(maxlen=int(RAW_WINDOW_S * FS))
        self._panel = ""
        self._mensajes = deque(maxlen=MAXIMO_MENSAJES)

    # ------------------------------------------------------------------
    # Estado completo (al abrir la ventana)
    # ------------------------------------------------------------------

    def obtener_estado(self):
        return para_json({
            "tipo": "estado",
            "tarea": self._tarea,
            "conexion": self._conexion,
            "calibracion": self._calibracion,
            "mvc_rms": self._mvc,
            "grabacion": self._grabacion,
            "alerta": dict(self._alerta, umbral=self._ajustes["umbral_alerta"],
                           rearme_min=self._ajustes["rearme_alerta_min"],
                           en_pausa=self._alerta_en_pausa()),
            "simulacion": {"modo": self._ajustes["modo_simulacion"],
                           "velocidad": self._ajustes["velocidad_simulacion"],
                           "velocidades": list(VELOCIDADES_SIMULACION),
                           "por_defecto": self._simular_por_defecto},
            "parametros": {"intervalo_s": TREND_INTERVAL_S, "ventana_tendencia_s": TREND_WINDOW_S,
                           "ventana_cruda_s": RAW_WINDOW_S, "ventana_bloques_s": BLOCK_WINDOW_S,
                           "reposo_s": REST_CHECK_S, "duracion_maxima_s": DURACION_MAXIMA_S},
            "tendencias": list(self._tendencias),
            "bloques": list(self._bloques),
            "crudo": list(self._crudo),
            "panel": self._panel,
            "mensajes": list(self._mensajes),
            "carpeta_datos": str(self._carpeta),
        })

    # ------------------------------------------------------------------
    # Conexión
    # ------------------------------------------------------------------

    def listar_puertos(self):
        try:
            detectados = self._buscar_puertos()
            return {"detectados": detectados, "todos": todos_los_puertos(detectados)}
        except Exception as error:
            return {"detectados": [], "todos": [], "error": str(error)}

    def conectar(self, opciones):
        """opciones: {"simulacion": bool, "puerto": str o null (= automático), "modo", "velocidad"}."""
        if self._ocupada():
            return self._respuesta_ocupada()
        self._cerrar_dispositivo()
        self._reposo = None
        self._mvc = None
        self._calibracion = {"estado": "pendiente", "progreso": 0.0, "lineas": []}
        if opciones.get("simulacion"):
            return self._conectar_simulador(opciones)
        return self._iniciar_tarea(CONECTANDO, self._conectar_bitalino, opciones.get("puerto") or None)

    def _conectar_simulador(self, opciones):
        modo = opciones.get("modo") or self._ajustes["modo_simulacion"]
        velocidad = float(opciones.get("velocidad") or self._ajustes["velocidad_simulacion"])
        try:
            self._dispositivo = BITalinoSimulado(velocidad=velocidad, modo=modo)
        except ValueError as error:
            return {"ok": False, "mensaje": str(error)}
        self._ajustes.update(modo_simulacion=modo, velocidad_simulacion=velocidad)
        guardar_ajustes(self._ajustes, self._carpeta)
        self._conexion = {"estado": "Conectado", "detalle": f"Simulación · modo {modo} · ×{velocidad:g}",
                          "puerto": None, "version": self._dispositivo.version(), "simulado": True}
        self._anotar(f"Simulación: modo {modo}, velocidad {velocidad:g}x.")
        self._enviar_estado()
        return {"ok": True}

    def _conectar_bitalino(self, puerto):
        self._conexion = {"estado": "Conectando", "detalle": "Buscando el BITalino…", "puerto": None,
                          "version": None, "simulado": False}
        self._enviar_estado()

        def avisar(texto):
            self._conexion["detalle"] = texto
            self._enviar_estado()

        try:
            if puerto:
                avisar(f"Probando {puerto}…")
                dispositivo = self._abrir_bitalino(puerto, TIEMPO_LIMITE_CONEXION_S, self._detener)
            else:
                candidatos = lista_candidatos(self._ajustes["ultimo_puerto"], PUERTO, self._buscar_puertos())
                dispositivo = conectar_automatico(candidatos, TIEMPO_LIMITE_CONEXION_S, self._detener,
                                                  self._abrir_bitalino, avisar)
        except InterruptedError:
            self._conexion.update(estado="Desconectado", detalle="Conexión cancelada.")
            return
        except LookupError as error:
            self._conexion.update(estado="Error", detalle=str(error))
            return
        except Exception as error:
            self._conexion.update(estado="Error", detalle=explicar_error(puerto, error))
            return
        dispositivo.detener = None  # desde aquí, Detener no corta las lecturas a la mitad
        self._dispositivo = dispositivo
        self._ajustes["ultimo_puerto"] = dispositivo.puerto
        guardar_ajustes(self._ajustes, self._carpeta)
        self._conexion = {"estado": "Conectado", "detalle": "", "puerto": dispositivo.puerto,
                          "version": dispositivo.version(), "simulado": False}
        self._anotar(f"Conectado al BITalino en {dispositivo.puerto} ({dispositivo.version()}).")

    def desconectar(self):
        if self._ocupada():
            return self._respuesta_ocupada()
        self._cerrar_dispositivo()
        self._enviar_estado()
        return {"ok": True}

    def _cerrar_dispositivo(self):
        if self._dispositivo is not None:
            try:
                self._dispositivo.close()
            except Exception:
                pass
        self._dispositivo = None
        self._conexion = {"estado": "Desconectado", "detalle": "", "puerto": None, "version": None, "simulado": False}

    # ------------------------------------------------------------------
    # Calibración (botón Calibrar) y MVC (pestaña Detalles)
    # ------------------------------------------------------------------

    def calibrar(self):
        if self._dispositivo is None:
            return {"ok": False, "mensaje": "Primero conecta el dispositivo."}
        return self._iniciar_tarea(CALIBRANDO, self._calibrar)

    def _calibrar(self):
        self._calibracion = {"estado": "midiendo", "progreso": 0.0, "lineas": []}
        self._enviar_estado()

        def avisar_progreso(fraccion):
            self._calibracion["progreso"] = fraccion
            self._enviar_estado()

        self._preparar_dispositivo()
        try:
            reposo = comprobar_reposo(self._dispositivo, self._detener, avisar_progreso)
        except InterruptedError:
            self._calibracion = {"estado": "pendiente", "progreso": 0.0, "lineas": ["Calibración cancelada."]}
            return
        except Exception as error:
            self._calibracion = {"estado": "error", "progreso": 0.0, "lineas": [f"No se pudo calibrar: {error}"]}
            self._anotar(f"No se pudo calibrar: {error}")
            return
        self._reposo = reposo
        self._calibracion = {"estado": reposo.texto_estado, "progreso": 1.0, "lineas": reposo.lineas,
                             "motivos": reposo.motivos,
                             "umbral_actividad": umbral_actividad(reposo.rms_mediana, reposo.rms_sd_robusta)}
        for linea in reposo.lineas:
            self._anotar(linea)

    def calibrar_mvc(self):
        if self._dispositivo is None:
            return {"ok": False, "mensaje": "Primero conecta el dispositivo."}
        return self._iniciar_tarea(CALIBRANDO_MVC, self._calibrar_mvc)

    def _calibrar_mvc(self):
        self._preparar_dispositivo()
        try:
            self._mvc = calibrar_mvc(self._dispositivo, self._reposo, self._detener, self._anotar_y_enviar)
        except InterruptedError:
            self._anotar_y_enviar("Calibración de MVC cancelada.")
        except Exception as error:
            self._anotar_y_enviar(f"No se pudo calibrar la MVC: {error}")

    def borrar_mvc(self):
        if self._ocupada():
            return self._respuesta_ocupada()
        self._mvc = None
        self._enviar_estado()
        return {"ok": True}

    # ------------------------------------------------------------------
    # Grabación (botones Comenzar y Detener)
    # ------------------------------------------------------------------

    def comenzar(self):
        if self._dispositivo is None:
            return {"ok": False, "mensaje": "Primero conecta el dispositivo."}
        if self._reposo is None:
            return {"ok": False, "mensaje": "Primero calibra: aprieta Calibrar y mantén el músculo en reposo."}
        return self._iniciar_tarea(GRABANDO, self._grabar)

    def _grabar(self):
        rearme_s = self._ajustes["rearme_alerta_min"] * SEGUNDOS_POR_MINUTO
        self._analizador = AnalizadorFatiga(self._reposo, self._ajustes["umbral_alerta"], self._mvc, rearme_s)
        archivos = archivos_siguientes(self._carpeta)
        self._tendencias.clear()
        self._bloques.clear()
        self._crudo.clear()
        self._panel = ""
        self._grabacion = {"id": self._grabacion["id"] + 1, "activa": True, "tiempo_s": 0.0,
                           "archivos": archivos.como_lista(), "mensaje": "Grabando…"}
        self._anotar(f"Grabación {archivos.tendencias.stem}: hasta apretar Detener.")
        if not self._reposo.paso:
            self._anotar("WARN: la calibración no fue PASS; el índice de fatiga quedará suprimido.")
        self._enviar_estado()
        self._preparar_dispositivo()

        def publicar(estado, resultado, mediciones, final):
            self._publicar_bloque(estado, resultado, mediciones, final, archivos)

        try:
            estado = grabar(self._dispositivo, self._analizador, archivos, self._detener, publicar)
            self._grabacion["mensaje"] = (
                f"Grabación guardada ({estado.n_medicion * PERIODO:.0f} s). Clipped: {estado.clipping_count_recording}."
            )
        except Exception as error:
            self._grabacion["mensaje"] = f"La grabación se detuvo por un error: {error}. Los CSV quedaron guardados."
            self._conexion.update(estado="Error", detalle=str(error))
        finally:
            self._grabacion["activa"] = False
            self._anotar(self._grabacion["mensaje"])
            if self._conexion["simulado"]:
                self._anotar("AVISO: estos datos son SIMULADOS.")

    def detener(self):
        """Detiene la tarea en curso (grabación, calibración o conexión)."""
        self._detener.set()
        return {"ok": True}

    def _publicar_bloque(self, estado, resultado, mediciones, final, archivos):
        resumenes = [r for r in ((resultado.resumen if resultado else None), final) if r is not None]
        for resumen in resumenes:
            punto = [resumen.tiempo, resumen.rms, resumen.mdf, resumen.fatiga]
            self._tendencias.append(punto)
            for mensaje in resumen.mensajes:
                self._anotar(mensaje)
            self._enviar({"tipo": "tendencia", "punto": punto, "parcial": resumen.parcial, "calidad": resumen.calidad})
            if resumen.alerta:
                self._mostrar_alerta(resumen)
        if resultado is None:
            return
        bloque = [resultado.tiempo, resultado.rms, resultado.mdf, resultado.fatiga, resultado.activo]
        self._bloques.append(bloque)
        self._crudo.extend(mediciones)
        self._panel = texto_panel(estado, self._analizador, self._dispositivo, archivos)
        self._grabacion["tiempo_s"] = estado.n_medicion * PERIODO
        self._enviar({
            "tipo": "bloque",
            "bloque": bloque,
            "crudo": mediciones,
            "tiempo_s": self._grabacion["tiempo_s"],
            "calidad": resultado.calidad,
            "asentamiento": resultado.asentamiento,
            "panel": self._panel,
            "alerta": self._estado_alerta(),
        })

    # ------------------------------------------------------------------
    # Alerta de fatiga
    # ------------------------------------------------------------------

    def _mostrar_alerta(self, resumen):
        self._alerta = {"pendiente": True, "indice": resumen.fatiga, "tiempo_s": resumen.tiempo}
        self._enviar({"tipo": "alerta", "alerta": self._estado_alerta()})
        if self._crear_popup:
            self._crear_popup()

    def datos_alerta(self):
        """Lo que muestra el pop-up."""
        return para_json(self._estado_alerta())

    def cerrar_alerta(self):
        """El usuario cerró el pop-up (Aceptar o la X): la alerta se rearma después de la pausa."""
        if not self._alerta["pendiente"]:
            return {"ok": True}
        self._alerta["pendiente"] = False
        if self._analizador is not None:
            self._analizador.cerrar_alerta()
        if self._cerrar_popup:
            self._cerrar_popup()
        self._anotar(f"Alerta cerrada. Vuelve a estar disponible en {self._ajustes['rearme_alerta_min']:g} min de grabación.")
        self._enviar_estado()
        return {"ok": True}

    def _alerta_en_pausa(self):
        analizador = self._analizador
        return bool(analizador and analizador.alerta_fatiga_activada and not self._alerta["pendiente"])

    def _estado_alerta(self):
        return dict(self._alerta, umbral=self._ajustes["umbral_alerta"],
                    rearme_min=self._ajustes["rearme_alerta_min"], en_pausa=self._alerta_en_pausa())

    def cambiar_umbral(self, valor):
        """"Porcentaje de alerta": se aplica enseguida, también durante la grabación."""
        try:
            valor = float(valor)
        except (TypeError, ValueError):
            return {"ok": False, "mensaje": "Escribe un número entre 0 y 100."}
        if not 0 <= valor <= 100:
            return {"ok": False, "mensaje": "El porcentaje de alerta debe estar entre 0 y 100."}
        self._ajustes["umbral_alerta"] = valor
        guardar_ajustes(self._ajustes, self._carpeta)
        if self._analizador is not None:
            self._analizador.umbral_alerta = valor
        self._enviar_estado()
        return {"ok": True}

    def restaurar_umbral(self):
        return self.cambiar_umbral(FATIGUE_ALERT_THRESHOLD)

    # ------------------------------------------------------------------
    # Otros
    # ------------------------------------------------------------------

    def abrir_carpeta_datos(self):
        try:
            abrir_carpeta(self._carpeta)
            return {"ok": True}
        except Exception as error:
            return {"ok": False, "mensaje": f"No se pudo abrir la carpeta: {error}"}

    # --- Tareas en un hilo aparte ---

    def _ocupada(self):
        return self._hilo is not None and self._hilo.is_alive()

    def _respuesta_ocupada(self):
        return {"ok": False, "mensaje": "Espera a que termine lo que está en curso (o aprieta Detener)."}

    def _iniciar_tarea(self, nombre, funcion, *argumentos):
        with self._candado:
            if self._cerrando.is_set():
                return {"ok": False, "mensaje": "La app se está cerrando."}
            if self._ocupada():
                return self._respuesta_ocupada()
            self._detener.clear()
            self._tarea = nombre
            self._hilo = threading.Thread(target=self._ejecutar_tarea, args=(funcion, argumentos),
                                          name=f"rsi-{nombre}", daemon=True)
            self._hilo.start()
        return {"ok": True}

    def _ejecutar_tarea(self, funcion, argumentos):
        try:
            funcion(*argumentos)
        except Exception as error:
            traceback.print_exc()
            self._anotar(f"Error inesperado: {error}")
        finally:
            self._tarea = None
            self._enviar_estado()

    def _preparar_dispositivo(self):
        """El simulador corta su espera con Detener; el BITalino real termina la lectura en curso."""
        if isinstance(self._dispositivo, BITalinoSimulado):
            self._dispositivo.detener = self._detener

    # --- Mensajes a la ventana ---

    def _anotar(self, texto):
        self._mensajes.append(texto)

    def _anotar_y_enviar(self, texto):
        self._anotar(texto)
        self._enviar({"tipo": "mensaje", "texto": texto})

    def _enviar_estado(self):
        self._enviar(self.obtener_estado())

    def _enviar(self, mensaje):
        if self._enviar_js is None or self._cerrando.is_set():
            return
        texto = json.dumps(para_json(mensaje), allow_nan=False, ensure_ascii=False)
        try:
            self._enviar_js(f"window.rsi && window.rsi.recibir({texto});")
        except Exception as error:
            print(f"No se pudo actualizar la ventana: {error}", file=sys.stderr)

    def _cerrar(self):
        """La ventana principal se cierra: se detiene todo y se libera el BITalino."""
        self._cerrando.set()
        self._detener.set()
        if self._hilo is not None:
            self._hilo.join()
        self._cerrar_dispositivo()
        if self._cerrar_popup:
            self._cerrar_popup()


class Ventanas:
    """Crea la ventana principal y el pop-up de alerta con pywebview."""

    def __init__(self, api, depurar=False):
        import webview

        self.webview = webview
        self.api = api
        self.depurar = depurar
        self.popup = None
        self.principal = webview.create_window(
            NOMBRE_APP, str(CARPETA_INTERFAZ / "index.html"), js_api=api,
            width=TAMANO_VENTANA[0], height=TAMANO_VENTANA[1], min_size=TAMANO_MINIMO,
            background_color="#f4f6fa",
        )
        api._enviar_js = self.principal.evaluate_js
        api._crear_popup = self.abrir_popup
        api._cerrar_popup = self.cerrar_popup
        self.principal.events.closing += api._cerrar

    def abrir_popup(self):
        if self.popup is not None:
            return
        self.popup = self.webview.create_window(
            TITULO_ALERTA, str(CARPETA_INTERFAZ / "alerta.html"), js_api=self.api,
            width=TAMANO_ALERTA[0], height=TAMANO_ALERTA[1], resizable=False, on_top=True,
            background_color="#ffffff",
        )
        self.popup.events.closed += self.al_cerrar_popup

    def al_cerrar_popup(self):
        # Cerrar con la X de la ventana cuenta como cerrar la alerta.
        self.popup = None
        self.api.cerrar_alerta()

    def cerrar_popup(self):
        popup, self.popup = self.popup, None
        if popup is not None:
            try:
                popup.destroy()
            except Exception:
                pass

    def iniciar(self):
        opciones = {"gui": "edgechromium"} if sys.platform == "win32" else {}
        self.webview.start(http_server=True, debug=self.depurar, **opciones)


def principal(argumentos=None):
    lector = argparse.ArgumentParser(description="RSI Monitor: detector de fatiga muscular con BITalino.")
    lector.add_argument("--simular", action="store_true", help="proponer la simulación al conectar")
    lector.add_argument("--depurar", action="store_true", help="abrir las herramientas de desarrollo")
    argumentos = lector.parse_args(argumentos)
    api = Api(simular=argumentos.simular)
    ventanas = Ventanas(api, argumentos.depurar)
    ventanas.iniciar()
    api._cerrar()
    return 0


if __name__ == "__main__":
    sys.exit(principal())
