"""
Servicio: une todas las piezas del backend. main.py solo traduce rutas a llamadas de aquí.

- Encender: crea una SesionMedicion (BITalino real o simulado) y la corre en un hilo
  aparte, porque la lectura del BITalino es bloqueante.
- El hilo avisa lo que pasa a un OyenteWeb, que pasa cada aviso al bucle de asyncio con
  loop.call_soon_threadsafe(). Así, todo el estado se cambia en un solo hilo (el del
  bucle) y FastAPI nunca se bloquea.
- Cada aviso se convierte en un mensaje (ver mensajes.py) que se envía a todos los
  navegadores conectados al WebSocket.
- Una tarea corre cada segundo: avanza el reloj de uso, termina el descanso cuando se
  cumple el tiempo y envía el mensaje "reloj".
- Panel de conexión: con la medición apagada, "Reconectar" (un puerto) o "Detectar
  automáticamente" conectan el BITalino en un hilo y lo dejan listo para el próximo
  Encender. Si la conexión se corta midiendo, la sesión lo busca sola con espera
  creciente; elegir un puerto en ese momento hace que se pruebe primero.

Alerta de fatiga (la regla está en nucleo/regla_fatiga.py):
    alerta -> pendiente (sin duplicados) -> Aceptar -> descanso -> fin -> la alerta se rearma

Qué se puede editar aquí: los textos de estado (APAGADO, RIESGO_FATIGA, EN_DESCANSO,
TEXTO_DOCKER) y TICK_S.
"""

import asyncio
import logging
import math
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from app import almacenamiento, mensajes
from app.almacenamiento import LIMITES_PARAMETROS, PARAMETROS_DETECCION, ArchivoDescansos, Configuracion
from app.nucleo import conexion
from app.nucleo.adquisicion import BUSCANDO, CALIBRANDO, CONECTANDO, DESCONECTADO, ERROR, MIDIENDO, Oyente, SesionMedicion, prefijo_csv
from app.nucleo.cargador_original import cargar_original
from app.nucleo.conexion import BitalinoConLimite, ConectorBitalino, explicar_error, puertos_detectados
from app.nucleo.regla_fatiga import ACLARACION_MEDICA
from app.nucleo.simulador import DispositivoSimulado
from app.estado import EstadoApp
from app.textos import texto_alerta, texto_calibracion, texto_linea_base, texto_panel
from app.uso.descansos import GestorDescansos, PlantillasDescanso, validar_minutos
from app.uso.reloj_uso import RelojUso, formato_reloj

TICK_S = 1  # cada cuántos segundos corre la tarea del reloj
ESPERA_FIN_HILO_S = 5  # al cerrar el servidor, cuánto se espera a que termine la medición

# Estados de la app que no vienen de la medición
APAGADO = "Apagado"
RIESGO_FATIGA = "Riesgo de fatiga: descanso pendiente"
EN_DESCANSO = "En descanso"

TEXTO_DOCKER = (
    "El backend corre dentro de Docker, que no puede usar el Bluetooth del computador. "
    "Aquí solo se puede usar la simulación."
)

# Estado de la medición -> estado de la conexión que muestra el panel
CONEXION_SEGUN_MEDICION = {
    DESCONECTADO: "Desconectado",
    BUSCANDO: "Buscando",
    CONECTANDO: "Conectando",
    CALIBRANDO: "Conectado",
    MIDIENDO: "Conectado",
    ERROR: "Error",
}

registro = logging.getLogger("rsi_monitor")


class ErrorServicio(Exception):
    """Un pedido que no se puede cumplir ahora (la API responde 409)."""


def esta_en_docker():
    return os.environ.get("RSI_EN_DOCKER") == "1" or Path("/.dockerenv").exists()


def numero(valor):
    """NaN o infinito -> None (en el JSON va como null)."""
    if valor is None or not math.isfinite(valor):
        return None
    return float(valor)


class OyenteWeb(Oyente):
    """Corre en el hilo de medición: pasa cada aviso al bucle de asyncio."""

    def __init__(self, servicio):
        self.servicio = servicio

    def al_cambiar_estado(self, estado, detalle=""):
        self.servicio.desde_hilo(self.servicio.al_cambiar_estado, estado, detalle)

    def al_procesar_bloque(self, info):
        self.servicio.desde_hilo(self.servicio.al_procesar_bloque, info)

    def al_cerrar_intervalo(self, resumen, linea_base):
        self.servicio.desde_hilo(self.servicio.al_cerrar_intervalo, resumen, linea_base)

    def al_detectar_fatiga(self, resumen):
        self.servicio.desde_hilo(self.servicio.al_detectar_fatiga, resumen)

    def al_conectar(self, puerto, version):
        self.servicio.desde_hilo(self.servicio.al_conectar, puerto, version)


class Servicio:
    def __init__(
        self,
        original,
        configuracion,
        archivo_descansos,
        carpeta_datos,
        en_docker=False,
        modo_preferido="real",
        ahora=datetime.now,
        reloj=time.monotonic,
    ):
        self.original = original
        self.constantes = original.constantes
        self.configuracion = configuracion
        self.carpeta_datos = Path(carpeta_datos)
        self.en_docker = en_docker
        self.modo_preferido = "simulacion" if en_docker else modo_preferido

        memoria = configuracion["memoria"]
        self.estado = EstadoApp(memoria["max_puntos_tendencia"], memoria["max_bloques"])
        self.descansos = GestorDescansos(archivo_descansos, ahora=ahora)
        self.plantillas = PlantillasDescanso(archivo_descansos)
        self.reloj_uso = RelojUso(archivo_descansos, configuracion["reloj_uso"]["guardar_cada_s"], reloj=reloj)

        self.clientes = set()  # una asyncio.Queue por navegador conectado
        self.loop = None
        self.sesion = None
        self.hilo = None
        self.conector = None  # ConectorBitalino de la sesión real en curso
        self.hilo_conexion = None  # hilo de "Reconectar" con la medición apagada
        self.detener_conexion = None
        self.dispositivo_listo = None  # BITalino ya conectado, esperando Encender
        # Cómo se abre y se busca el BITalino real (las pruebas ponen uno falso).
        self.abrir_bitalino = BitalinoConLimite
        self.buscar_puertos = puertos_detectados

    # --- Ciclo de vida del servidor ---

    def iniciar(self, loop):
        self.loop = loop

    async def tarea_cada_segundo(self):
        while True:
            await asyncio.sleep(TICK_S)
            self.cada_segundo()

    def cerrar(self):
        """Al detener el servidor: apaga la medición y guarda el descanso y el reloj."""
        sesion, hilo = self.sesion, self.hilo
        if sesion is not None:
            sesion.detener()
            hilo.join(ESPERA_FIN_HILO_S)
        if self.detener_conexion is not None:
            self.detener_conexion.set()
        self.cerrar_dispositivo_listo()
        if self.descansos.en_descanso():
            self.descansos.terminar(completado=False)
        self.reloj_uso.terminar_medicion()

    def desde_hilo(self, funcion, *argumentos):
        """Pide al bucle de asyncio que ejecute funcion(*argumentos). Se llama desde otro hilo."""
        try:
            self.loop.call_soon_threadsafe(funcion, *argumentos)
        except (AttributeError, RuntimeError):
            pass  # el servidor ya se cerró

    # --- Navegadores conectados al WebSocket ---

    def agregar_cliente(self):
        cola = asyncio.Queue(maxsize=self.configuracion["servidor"]["max_mensajes_en_cola"])
        self.clientes.add(cola)
        return cola

    def quitar_cliente(self, cola):
        self.clientes.discard(cola)

    def enviar(self, mensaje):
        """Envía un mensaje a todos los navegadores."""
        if not self.clientes:
            return
        texto = mensaje.model_dump_json()
        for cola in list(self.clientes):
            try:
                cola.put_nowait(texto)
            except asyncio.QueueFull:
                # El navegador no alcanza a leer: se le corta la conexión. Al volver a
                # conectarse recibe la foto completa, así que no pierde nada importante.
                while not cola.empty():
                    cola.get_nowait()
                cola.put_nowait(None)
                self.clientes.discard(cola)

    # --- Medición ---

    def encender(self, pedido):
        if self.sesion is not None:
            raise ErrorServicio("La medición ya está encendida.")
        if self.hilo_conexion is not None:
            raise ErrorServicio("Se está conectando el BITalino: esperen a que termine.")
        simulacion = pedido.modo == "simulacion"
        if not simulacion and self.en_docker:
            raise ErrorServicio(TEXTO_DOCKER)
        if simulacion:
            self.cerrar_dispositivo_listo()

        escenario = velocidad = None
        umbrales_sim = False
        if simulacion:
            escenario, velocidad, umbrales_sim = self.opciones_simulacion(pedido)

            def abrir_dispositivo(detener, avisar):
                return DispositivoSimulado(
                    escenario,
                    self.original.fs,
                    inicio_rampa_s=self.constantes["SIM_BASELINE_DURATION_S"],
                    velocidad=velocidad or None,
                )

        else:
            abrir_dispositivo = self.abridor_real()

        parametros = self.configuracion.parametros_deteccion(self.constantes, umbrales_sim)
        sesion = SesionMedicion(
            self.original,
            parametros,
            abrir_dispositivo,
            almacenamiento.carpeta_datos(self.carpeta_datos),
            prefijo_csv(self.constantes, simulacion),
            OyenteWeb(self),
            reconectar=not simulacion,
        )
        self.estado.nueva_sesion(pedido.modo, escenario, velocidad, umbrales_sim, parametros, str(sesion.ruta_csv))
        self.sesion = sesion
        self.descansos.conectar_medicion(sesion)
        self.reloj_uso.empezar_medicion()

        self.hilo = threading.Thread(target=self.ejecutar_sesion, args=(sesion,), name="medicion", daemon=True)
        self.hilo.start()
        self.enviar(self.foto())

    def abridor_real(self):
        """
        Función abrir_dispositivo() para el BITalino real: la primera vez usa el que dejó
        listo el panel de conexión (si hay); después lo busca con el ConectorBitalino.
        """
        self.conector = self.crear_conector()
        listo = [self.dispositivo_listo]
        self.dispositivo_listo = None

        def abrir_dispositivo(detener, avisar):
            dispositivo = listo.pop() if listo else None
            if dispositivo is not None:
                dispositivo.detener = detener  # para que Apagar corte sus lecturas
                return dispositivo
            return self.conector(detener, avisar)

        return abrir_dispositivo

    def opciones_simulacion(self, pedido):
        """Escenario, velocidad y umbrales del pedido; lo que no viene sale de config.json."""
        ajustes = self.configuracion["simulacion"]
        escenario = pedido.escenario or self.configuracion.escenario_simulacion(self.constantes)
        velocidad = ajustes["velocidad"] if pedido.velocidad is None else pedido.velocidad
        umbrales_sim = ajustes["usar_umbrales_sim"] if pedido.umbrales_sim is None else pedido.umbrales_sim

        # Se recuerda lo elegido para la próxima vez (la velocidad 0 es solo para pruebas).
        if pedido.escenario is not None:
            ajustes["escenario"] = pedido.escenario
        if pedido.velocidad:
            ajustes["velocidad"] = pedido.velocidad
        ajustes["usar_umbrales_sim"] = umbrales_sim
        self.configuracion.guardar()
        return escenario, velocidad, umbrales_sim

    def ejecutar_sesion(self, sesion):
        """Corre en el hilo de medición."""
        try:
            sesion.ejecutar()
        except Exception:
            # La sesión ya avisó el estado Error con el detalle; aquí se deja el rastro.
            registro.exception("La medición se detuvo por un error")
        finally:
            self.desde_hilo(self.al_terminar_sesion, sesion)

    def apagar(self):
        if self.sesion is None:
            raise ErrorServicio("La medición ya está apagada.")
        # El hilo cierra el último intervalo, llama a stop() y avisa con al_terminar_sesion().
        self.sesion.detener()

    # --- Avisos del hilo de medición (corren en el bucle de asyncio) ---

    def al_cambiar_estado(self, estado, detalle=""):
        self.estado.estado_medicion = estado
        if estado == ERROR:
            detalle = f"La medición se detuvo por un error: {detalle}"
        self.al_cambiar_conexion(estado, detalle)

    def al_cambiar_conexion(self, estado, detalle=""):
        """estado: un estado de la medición (Buscando, Conectando, Midiendo...)."""
        if estado in CONEXION_SEGUN_MEDICION:
            self.estado.estado_conexion = CONEXION_SEGUN_MEDICION[estado]
            self.estado.detalle_conexion = detalle
        self.enviar(self.mensaje_conexion())

    def al_conectar(self, puerto, version):
        self.estado.puerto = puerto
        self.estado.version = version
        if puerto:
            self.configuracion["conexion"]["ultimo_puerto"] = puerto
            self.configuracion.guardar()
        self.enviar(self.mensaje_conexion())

    def al_procesar_bloque(self, info):
        bloque = mensajes.Bloque(
            n_medicion=info.n_medicion,
            ultimo_valor_emg=numero(info.ultimo_valor_emg),
            ultimo_rms=numero(info.ultimo_rms),
            ultimo_mdf=numero(info.ultimo_mdf),
            muestras_recientes=[mensajes.Muestra(tiempo=t, valor=v) for t, v in info.muestras_recientes],
            texto_panel=texto_panel(info, self.constantes, self.estado.parametros, self.estado.estado_medicion),
        )
        self.estado.bloques.append(bloque)
        self.enviar(mensajes.MensajeBloque(bloque=bloque))

    def al_cerrar_intervalo(self, resumen, linea_base):
        punto = mensajes.PuntoTendencia(tiempo=resumen.tiempo, rms=numero(resumen.rms), mdf=numero(resumen.mdf))
        self.estado.tendencia.append(punto)
        self.estado.linea_base = linea_base
        self.enviar(
            mensajes.MensajeTendencia(estado_app=self.estado_app(), punto=punto, calibracion=self.calibracion())
        )

    def al_detectar_fatiga(self, resumen):
        # recibir_alerta() devuelve False si ya hay una pendiente: así no se duplica.
        if self.descansos.recibir_alerta():
            registro.info("Alerta de fatiga en t=%.1f s", resumen.tiempo)
            self.enviar(mensajes.MensajeAlerta(estado_app=self.estado_app(), alerta=self.info_alerta()))

    def al_terminar_sesion(self, sesion):
        if sesion is not self.sesion:
            return
        self.sesion = None
        self.hilo = None
        self.conector = None
        self.estado.encendida = False
        if self.estado.estado_conexion != "Error":
            self.estado.estado_conexion = "Desconectado"
            self.estado.detalle_conexion = ""
        self.descansos.conectar_medicion(None)
        self.reloj_uso.terminar_medicion()
        self.enviar(self.foto())

    # --- Alerta y descansos ---

    def minutos_descanso_fatiga(self):
        return self.configuracion["descansos"]["duracion_fatiga_min"]

    def aceptar_alerta(self):
        if not self.descansos.alerta_pendiente:
            raise ErrorServicio("No hay una alerta pendiente.")
        self.descansos.aceptar_alerta(self.minutos_descanso_fatiga())
        self.reloj_uso.empezar_descanso()
        self.enviar(mensajes.MensajeAlerta(estado_app=self.estado_app(), alerta=self.info_alerta()))
        self.enviar_descanso("iniciado")

    def iniciar_descanso(self, pedido):
        nombre = None
        minutos = pedido.minutos
        if pedido.plantilla is not None:
            plantilla = self.plantilla(pedido.plantilla)
            nombre, minutos = plantilla["nombre"], plantilla["duracion_min"]
        if minutos is None:
            raise ValueError("Elijan una plantilla o una duración en minutos.")
        if self.descansos.alerta_pendiente:
            raise ErrorServicio("Hay una alerta de fatiga pendiente: acéptenla para empezar el descanso.")
        if self.descansos.en_descanso():
            raise ErrorServicio("Ya hay un descanso en curso.")
        self.descansos.iniciar_manual(minutos, nombre)
        self.reloj_uso.empezar_descanso()
        self.enviar_descanso("iniciado")

    def terminar_descanso(self, completado=False):
        if not self.descansos.en_descanso():
            raise ErrorServicio("No hay un descanso en curso.")
        # terminar() también quita la pausa de la regla y rearma la alerta.
        self.descansos.terminar(completado)
        self.reloj_uso.terminar_descanso()
        self.enviar_descanso("terminado", completado)

    def enviar_descanso(self, evento, completado=False):
        self.enviar(
            mensajes.MensajeDescanso(
                estado_app=self.estado_app(), evento=evento, completado=completado, descanso=self.info_descanso()
            )
        )

    def cada_segundo(self):
        self.reloj_uso.tick()
        if self.descansos.termino_el_tiempo():
            self.terminar_descanso(completado=True)
        self.enviar(
            mensajes.MensajeReloj(
                reloj=self.info_reloj(), segundos_restantes_descanso=self.descansos.segundos_restantes()
            )
        )

    # --- Plantillas e historial ---

    def plantilla(self, indice):
        lista = self.plantillas.lista()
        if not 0 <= indice < len(lista):
            raise IndexError("Esa plantilla no existe.")
        return lista[indice]

    def respuesta_plantillas(self):
        return mensajes.RespuestaPlantillas(plantillas=self.plantillas.lista())

    def crear_plantilla(self, plantilla):
        self.plantillas.agregar(plantilla.nombre, plantilla.duracion_min)
        return self.respuesta_plantillas()

    def editar_plantilla(self, indice, plantilla):
        self.plantilla(indice)
        self.plantillas.editar(indice, plantilla.nombre, plantilla.duracion_min)
        return self.respuesta_plantillas()

    def borrar_plantilla(self, indice):
        self.plantilla(indice)
        self.plantillas.borrar(indice)
        return self.respuesta_plantillas()

    def historial(self):
        return mensajes.RespuestaHistorial(
            historial=list(reversed(self.descansos.historial)),
            minutos_hoy=self.descansos.minutos_del_dia(),
            cantidad_hoy=len(self.descansos.descansos_del_dia()),
        )

    # --- Configuración ---

    def respuesta_config(self):
        parametros_usados = self.configuracion.parametros_deteccion(self.constantes)
        guardados = self.configuracion["parametros_deteccion"]
        return mensajes.RespuestaConfig(
            parametros=[
                mensajes.ParametroConfig(
                    nombre=nombre,
                    valor=parametros_usados[nombre],
                    original=self.constantes[nombre],
                    sim=self.constantes["SIM_" + nombre],
                    personalizado=guardados.get(nombre) is not None,
                    minimo=LIMITES_PARAMETROS[nombre][0],
                    maximo=LIMITES_PARAMETROS[nombre][1],
                )
                for nombre in PARAMETROS_DETECCION
            ],
            duracion_fatiga_min=self.minutos_descanso_fatiga(),
            usar_umbrales_sim=self.configuracion["simulacion"]["usar_umbrales_sim"],
            velocidades=self.configuracion["simulacion"]["velocidades"],
            TREND_WINDOW_S=self.constantes["TREND_WINDOW_S"],
        )

    def guardar_config(self, pedido):
        """Los parámetros de detección se usan desde el próximo Encender; el descanso, al instante."""
        cambios = dict(pedido.parametros or {})
        if pedido.restaurar:
            cambios = {nombre: None for nombre in PARAMETROS_DETECCION}
            por_defecto = self.configuracion.por_defecto["descansos"]["duracion_fatiga_min"]
            self.configuracion["descansos"]["duracion_fatiga_min"] = por_defecto
        for nombre, valor in cambios.items():
            if nombre not in PARAMETROS_DETECCION:
                raise ValueError(f"{nombre} no es un parámetro de detección.")
            self.configuracion.poner_parametro(nombre, valor, self.constantes)
        if pedido.duracion_fatiga_min is not None:
            validar_minutos(pedido.duracion_fatiga_min)
            self.configuracion["descansos"]["duracion_fatiga_min"] = pedido.duracion_fatiga_min
        if pedido.usar_umbrales_sim is not None:
            self.configuracion["simulacion"]["usar_umbrales_sim"] = pedido.usar_umbrales_sim
        self.configuracion.guardar()
        self.enviar(self.foto())
        return self.respuesta_config()

    # --- Panel de conexión ---

    def reconectar(self, pedido):
        """pedido.puerto: el puerto elegido, o None para detectar automáticamente."""
        if self.en_docker:
            raise ErrorServicio(TEXTO_DOCKER)
        if self.sesion is not None:
            self.reconectar_midiendo(pedido.puerto)
            return
        if self.hilo_conexion is not None:
            raise ErrorServicio("Ya se está buscando el BITalino.")

        self.cerrar_dispositivo_listo()
        self.detener_conexion = threading.Event()
        self.hilo_conexion = threading.Thread(
            target=self.conectar_en_hilo, args=(pedido.puerto, self.detener_conexion), name="conexion", daemon=True
        )
        self.al_cambiar_conexion(BUSCANDO if pedido.puerto is None else CONECTANDO, "")
        self.hilo_conexion.start()

    def reconectar_midiendo(self, puerto):
        if self.estado.modo != "real":
            raise ErrorServicio("En simulación no hay un BITalino que reconectar.")
        if self.estado.estado_conexion == "Conectado":
            raise ErrorServicio("El BITalino ya está conectado. Para cambiar de puerto, apaguen la medición.")
        self.conector.preferir(puerto)

    def crear_conector(self):
        return ConectorBitalino(
            self.configuracion["conexion"], self.constantes["PUERTO"], self.abrir_bitalino, self.buscar_puertos
        )

    def conectar_en_hilo(self, puerto, detener):
        """Corre en el hilo de conexión: un intento con el puerto elegido, o una vuelta por todos."""
        conexion = self.configuracion["conexion"]

        def avisar(estado, detalle=""):
            self.desde_hilo(self.al_cambiar_conexion, estado, detalle)

        try:
            if puerto is None:
                dispositivo = self.crear_conector().una_vuelta(detener, avisar)
            else:
                avisar(CONECTANDO, f"Probando {puerto}…")
                dispositivo = self.abrir_bitalino(puerto, conexion["timeout_s"], detener)
        except InterruptedError:
            dispositivo = None
        except LookupError as error:
            self.desde_hilo(self.al_fallar_conexion, str(error))
            return
        except Exception as error:
            self.desde_hilo(self.al_fallar_conexion, explicar_error(puerto, error))
            return
        self.desde_hilo(self.al_conectar_listo, dispositivo)

    def al_conectar_listo(self, dispositivo):
        self.hilo_conexion = None
        self.detener_conexion = None
        if dispositivo is None:  # se cerró el servidor mientras se conectaba
            self.al_cambiar_conexion("Desconectado")
            return
        self.dispositivo_listo = dispositivo
        self.estado.estado_conexion = "Conectado"
        self.estado.detalle_conexion = "Listo para medir: aprieten Encender."
        self.al_conectar(dispositivo.puerto, dispositivo.version())

    def al_fallar_conexion(self, texto):
        self.hilo_conexion = None
        self.detener_conexion = None
        self.estado.estado_conexion = "Error"
        self.estado.detalle_conexion = texto
        self.enviar(self.mensaje_conexion())

    def cerrar_dispositivo_listo(self):
        if self.dispositivo_listo is not None:
            self.dispositivo_listo.close()
            self.dispositivo_listo = None
            self.estado.estado_conexion = "Desconectado"
            self.estado.detalle_conexion = ""

    # --- Puertos ---

    def puertos(self):
        if self.en_docker:
            return mensajes.RespuestaPuertos(detectados=[], todos=[])
        return mensajes.RespuestaPuertos(detectados=conexion.puertos_detectados(), todos=conexion.todos_los_puertos())

    # --- Partes de los mensajes ---

    def estado_app(self):
        if self.descansos.alerta_pendiente:
            return RIESGO_FATIGA
        if self.descansos.en_descanso():
            return EN_DESCANSO
        if self.sesion is None:
            return APAGADO
        return self.estado.estado_medicion

    def parametros(self):
        """Los de la sesión en curso o, con la medición apagada, los que se usarían."""
        parametros = self.estado.parametros if self.sesion is not None else None
        if parametros is None:
            umbrales_sim = self.modo_preferido == "simulacion" and self.configuracion["simulacion"]["usar_umbrales_sim"]
            parametros = self.configuracion.parametros_deteccion(self.constantes, umbrales_sim)
        return mensajes.Parametros(TREND_WINDOW_S=self.constantes["TREND_WINDOW_S"], **parametros)

    def calibracion(self):
        linea_base = None
        if self.estado.linea_base is not None:
            rms, mdf = self.estado.linea_base
            linea_base = mensajes.LineaBase(rms=rms, mdf=mdf, texto=texto_linea_base(rms, mdf))
        return mensajes.Calibracion(
            calibrando=self.sesion is not None and self.estado.estado_medicion == CALIBRANDO,
            texto=texto_calibracion(self.parametros().BASELINE_DURATION_S),
            linea_base=linea_base,
        )

    def info_medicion(self):
        estado = self.estado
        return mensajes.InfoMedicion(
            encendida=self.sesion is not None,
            modo_preferido=self.modo_preferido,
            modo=estado.modo,
            escenario=estado.escenario,
            velocidad=estado.velocidad,
            umbrales_sim=estado.umbrales_sim,
            estado=estado.estado_medicion,
            ruta_csv=estado.ruta_csv,
        )

    def info_conexion(self):
        detalle = self.estado.detalle_conexion
        if self.en_docker and not detalle:
            detalle = TEXTO_DOCKER
        return mensajes.InfoConexion(
            estado=self.estado.estado_conexion,
            puerto=self.estado.puerto,
            version=self.estado.version,
            detalle=detalle,
            en_docker=self.en_docker,
        )

    def info_alerta(self):
        minutos = self.minutos_descanso_fatiga()
        return mensajes.InfoAlerta(
            pendiente=self.descansos.alerta_pendiente,
            texto=texto_alerta(minutos),
            aclaracion=ACLARACION_MEDICA,
            minutos=minutos,
        )

    def info_descanso(self):
        actual = self.descansos.actual
        return mensajes.InfoDescanso(
            activo=actual is not None,
            nombre=actual.nombre if actual else None,
            origen=actual.origen if actual else None,
            duracion_planeada_s=actual.duracion_planeada_s if actual else 0,
            segundos_restantes=self.descansos.segundos_restantes(),
            minutos_hoy=self.descansos.minutos_del_dia(),
            cantidad_hoy=len(self.descansos.descansos_del_dia()),
        )

    def info_reloj(self):
        segundos_hoy = self.reloj_uso.segundos_hoy()
        segundos_sesion = self.reloj_uso.segundos_sesion
        return mensajes.InfoReloj(
            segundos_hoy=segundos_hoy,
            segundos_sesion=segundos_sesion,
            texto_hoy=formato_reloj(segundos_hoy),
            texto_sesion=formato_reloj(segundos_sesion),
            corriendo=self.reloj_uso.corriendo(),
        )

    def mensaje_conexion(self):
        return mensajes.MensajeConexion(
            estado_app=self.estado_app(), medicion=self.info_medicion(), conexion=self.info_conexion()
        )

    def foto(self):
        """Foto completa del estado: lo primero que recibe un navegador al conectarse."""
        return mensajes.MensajeEstado(
            estado_app=self.estado_app(),
            medicion=self.info_medicion(),
            conexion=self.info_conexion(),
            parametros=self.parametros(),
            calibracion=self.calibracion(),
            tendencia=list(self.estado.tendencia),
            ultimo_bloque=self.estado.ultimo_bloque(),
            alerta=self.info_alerta(),
            descanso=self.info_descanso(),
            reloj=self.info_reloj(),
        )


def crear_servicio(carpeta_datos=None, en_docker=None, modo_preferido="real", **opciones):
    """
    Carga el original, config.json y descansos.json, y crea el Servicio.
    'opciones' (ahora, reloj) sirven para simular el paso del tiempo en las pruebas.
    """
    carpeta_datos = almacenamiento.carpeta_datos(carpeta_datos or almacenamiento.CARPETA_DATOS)
    configuracion = Configuracion(carpeta_datos)
    archivo_descansos = ArchivoDescansos(carpeta_datos, configuracion["descansos"]["plantillas_iniciales"])
    return Servicio(
        cargar_original(),
        configuracion,
        archivo_descansos,
        carpeta_datos,
        en_docker=esta_en_docker() if en_docker is None else en_docker,
        modo_preferido=modo_preferido,
        **opciones,
    )
