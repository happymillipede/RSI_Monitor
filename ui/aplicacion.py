"""
Coordinador de la app con ventana: conecta el hilo de medición con la ventana
principal, la alerta, los descansos, el reloj de uso y el ícono de la bandeja.

Aquí se decide qué hacer cuando el usuario aprieta algo y qué mostrar cuando el hilo
avisa algo. No hay procesamiento de señal (está en nucleo/) ni reglas de descansos o
del reloj de uso (están en uso/).

Qué se puede editar aquí: TIEMPO_MAXIMO_CIERRE_MS y los textos de los avisos.
"""

import sys

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox

from nucleo import rutas
from nucleo.adquisicion import CALIBRANDO, DESCONECTADO, ERROR, HiloAdquisicion, SesionMedicion, prefijo_csv
from nucleo.simulador import DispositivoSimulado
from ui.bandeja import ICONO_ALERTA, ICONO_APAGADO, ICONO_DESCANSO, ICONO_MIDIENDO, Bandeja, crear_icono
from sistema import autoinicio
from ui.cuenta_regresiva import VentanaCuentaRegresiva
from ui.dialogo_ajustes import NOTA_PARAMETROS, DialogoAjustes
from ui.dialogo_alerta import DialogoAlerta, texto_alerta
from ui.pestana_descansos import DialogoTomarDescanso, PestanaDescansos
from ui.ventana_principal import (
    EN_DESCANSO,
    RIESGO_FATIGA,
    TITULO_VENTANA,
    VentanaPrincipal,
    texto_calibracion,
    texto_descanso,
    texto_linea_base,
    texto_panel,
    texto_uso,
)
from uso.descansos import GestorDescansos, PlantillasDescanso
from uso.reloj_uso import RelojUso

# Al salir se espera a que el hilo cierre el dispositivo como máximo este tiempo.
TIEMPO_MAXIMO_CIERRE_MS = 5000
UN_SEGUNDO_MS = 1000

AVISO_SIGUE_EN_BANDEJA = (
    "RSI Monitor sigue funcionando en la bandeja. Para cerrarlo use Salir en el menú del ícono."
)
AVISO_FIN_DESCANSO = "Terminó el descanso. La detección de fatiga vuelve a estar activa."


class AplicacionRSI(QObject):
    def __init__(self, original, configuracion, carpeta_base, umbrales_sim_forzados=False):
        super().__init__()
        self.original = original
        self.constantes = original.constantes
        self.configuracion = configuracion
        self.carpeta_datos = rutas.carpeta_datos(carpeta_base)
        self.umbrales_sim_forzados = umbrales_sim_forzados

        self.hilo = None
        self.parametros = None
        self.estado = DESCONECTADO  # último estado que avisó el hilo de medición
        self.texto_detalle = ""  # lo que se vuelve a mostrar al terminar un descanso
        self.linea_base_mostrada = False
        self.aviso_bandeja_mostrado = False

        self.reloj_uso = RelojUso(self.carpeta_datos, configuracion["reloj_uso"]["guardar_cada_s"])
        self.descansos = GestorDescansos(self.carpeta_datos)
        self.plantillas = PlantillasDescanso(configuracion)

        self.crear_ventanas()
        self.crear_bandeja()
        # Empaquetada, el inicio con el sistema se deja como dice config.json (y se
        # actualiza la ruta si el .exe o la .app se movieron de carpeta).
        if rutas.esta_empaquetada():
            self.aplicar_autoinicio(avisar_error=False)

        self.temporizador = QTimer(self)
        self.temporizador.timeout.connect(self.cada_segundo)
        self.temporizador.start(UN_SEGUNDO_MS)

        self.mostrar_historial()
        self.actualizar_estado()

    def crear_ventanas(self):
        self.ventana = VentanaPrincipal(self.constantes["TREND_WINDOW_S"])
        simulacion = self.configuracion["simulacion"]
        self.ventana.poner_modo(
            simulacion["activa"],
            self.configuracion.escenario_simulacion(self.constantes),
            simulacion["velocidad"],
        )
        self.ventana.encender_apagar_pedido.connect(self.alternar_medicion)
        self.ventana.modo_cambiado.connect(self.guardar_modo)
        self.ventana.cerrada_por_usuario.connect(self.al_cerrar_ventana)
        self.ventana.descanso_pedido.connect(self.tomar_descanso)
        self.ventana.ajustes_pedido.connect(self.abrir_ajustes)
        self.ventana.carpeta_datos_pedida.connect(self.abrir_carpeta_datos)
        self.ventana.salir_pedido.connect(self.salir)

        self.pestana_descansos = PestanaDescansos(self.plantillas)
        self.pestana_descansos.tomar_descanso_pedido.connect(self.tomar_descanso)
        self.ventana.agregar_pestana(self.pestana_descansos, "Descansos")

        self.dialogo_alerta = DialogoAlerta()
        self.dialogo_alerta.accepted.connect(self.aceptar_alerta)

        self.cuenta_regresiva = VentanaCuentaRegresiva()
        self.cuenta_regresiva.terminar_antes_pedido.connect(lambda: self.terminar_descanso(completado=False))

    def crear_bandeja(self):
        # Si el sistema no tiene bandeja (pasa en algunos escritorios Linux), la app
        # funciona igual, pero cerrar la ventana cierra la app.
        self.bandeja = None
        if not Bandeja.disponible():
            return
        self.bandeja = Bandeja()
        self.bandeja.mostrar_pedido.connect(self.mostrar_ventana)
        self.bandeja.encender_apagar_pedido.connect(self.alternar_medicion)
        self.bandeja.descanso_pedido.connect(self.tomar_descanso)
        self.bandeja.salir_pedido.connect(self.salir)
        self.bandeja.show()

    # --- Encender / Apagar ---

    def alternar_medicion(self):
        if self.hilo is None:
            self.encender()
        elif not self.hilo.sesion.pedido_detener.is_set():
            self.apagar()

    def encender(self):
        simulacion = self.ventana.modo_simulacion()
        self.parametros = self.configuracion.parametros_deteccion(
            self.constantes, self.usar_umbrales_sim(simulacion)
        )
        sesion = SesionMedicion(
            self.original,
            self.parametros,
            self.funcion_abrir_dispositivo(simulacion),
            self.carpeta_datos,
            prefijo_csv(self.constantes, simulacion),
        )

        self.hilo = HiloAdquisicion(sesion)
        self.hilo.estado_cambiado.connect(self.al_cambiar_estado)
        self.hilo.bloque_procesado.connect(self.al_procesar_bloque)
        self.hilo.intervalo_cerrado.connect(self.al_cerrar_intervalo)
        self.hilo.fatiga_detectada.connect(self.al_detectar_fatiga)
        self.hilo.finished.connect(self.al_terminar_hilo)

        # Si se enciende durante un descanso, la medición parte con la alerta en pausa.
        self.descansos.conectar_medicion(self.hilo)
        self.reloj_uso.empezar_medicion()
        self.linea_base_mostrada = False

        self.ventana.medicion_iniciada(self.parametros["TREND_INTERVAL_S"])
        self.mostrar_detalle(f"Guardando en {sesion.ruta_csv.name}")
        self.poner_boton_bandeja("Apagar", activo=True)
        self.hilo.start()

    def apagar(self):
        # No se espera aquí al hilo: la ventana sigue respondiendo y
        # al_terminar_hilo() se llama cuando el hilo cierra el dispositivo.
        self.hilo.detener()
        self.ventana.apagando()
        self.poner_boton_bandeja("Apagando…", activo=False)

    def al_terminar_hilo(self):
        # La señal "finished" llega justo antes de que el hilo termine del todo:
        # se espera ese instante (milisegundos) antes de soltarlo.
        self.hilo.wait()
        self.hilo = None
        self.descansos.conectar_medicion(None)
        self.reloj_uso.terminar_medicion()
        self.ventana.medicion_detenida()
        self.poner_boton_bandeja("Encender", activo=True)
        self.actualizar_estado()

    def usar_umbrales_sim(self, simulacion):
        """Los umbrales SIM_* solo se usan en modo simulación y si se pidieron."""
        pedido = self.umbrales_sim_forzados or self.configuracion["simulacion"]["usar_umbrales_sim"]
        return simulacion and pedido

    def funcion_abrir_dispositivo(self, simulacion):
        """Devuelve la función que el hilo llama para obtener el dispositivo."""
        if simulacion:
            escenario = self.ventana.escenario()
            velocidad = self.ventana.velocidad()
            inicio_rampa_s = self.constantes["SIM_BASELINE_DURATION_S"]
            fs = self.original.fs
            return lambda: DispositivoSimulado(escenario, fs, inicio_rampa_s, velocidad)

        def abrir_bitalino_real():
            raise RuntimeError(
                "La conexión automática con el BITalino real se agrega en la Fase 6. "
                "Por ahora use el modo Simulación."
            )

        return abrir_bitalino_real

    def guardar_modo(self):
        simulacion = self.configuracion["simulacion"]
        simulacion["activa"] = self.ventana.modo_simulacion()
        simulacion["escenario"] = self.ventana.escenario()
        simulacion["velocidad"] = self.ventana.velocidad()
        self.configuracion.guardar()

    # --- Avisos del hilo de medición ---

    def al_cambiar_estado(self, estado, detalle):
        self.estado = estado
        self.actualizar_estado()
        if estado == CALIBRANDO:
            self.mostrar_detalle(texto_calibracion(self.parametros["BASELINE_DURATION_S"]))
        elif estado == ERROR:
            self.mostrar_detalle(detalle)

    def al_procesar_bloque(self, info):
        self.ventana.mostrar_panel(texto_panel(info, self.constantes, self.parametros, self.estado))

    def al_cerrar_intervalo(self, resumen, linea_base):
        self.ventana.agregar_intervalo(resumen)
        if linea_base is not None and not self.linea_base_mostrada:
            self.linea_base_mostrada = True
            self.mostrar_detalle(texto_linea_base(*linea_base))

    # --- Alerta de fatiga ---

    def al_detectar_fatiga(self, resumen):
        # No se repite si ya hay una alerta esperando Aceptar o un descanso en curso.
        if not self.descansos.recibir_alerta():
            return
        minutos = self.minutos_descanso_fatiga()
        self.dialogo_alerta.mostrar(minutos)
        self.notificar(texto_alerta(minutos), alerta=True)
        self.actualizar_estado()

    def aceptar_alerta(self):
        descanso = self.descansos.aceptar_alerta(self.minutos_descanso_fatiga())
        self.empezar_descanso(descanso)

    def minutos_descanso_fatiga(self):
        return self.configuracion["descansos"]["duracion_fatiga_min"]

    # --- Descansos ---

    def tomar_descanso(self):
        """Botón "Tomar descanso" (pestaña Descansos o bandeja)."""
        if self.descansos.alerta_pendiente:
            # Con una alerta pendiente, el descanso empieza con su botón Aceptar.
            self.dialogo_alerta.traer_al_frente()
            return
        if self.descansos.en_descanso():
            self.mostrar_cuenta_regresiva()
            return

        padre = self.ventana if self.ventana.isVisible() else None
        dialogo = DialogoTomarDescanso(self.plantillas.lista(), padre)
        if not dialogo.exec():
            return
        nombre, minutos = dialogo.valores()
        descanso = self.descansos.iniciar_manual(minutos, nombre)
        if descanso is not None:  # None si llegó una alerta mientras se elegía
            self.empezar_descanso(descanso)

    def empezar_descanso(self, descanso):
        self.reloj_uso.empezar_descanso()
        self.mostrar_cuenta_regresiva()
        self.ventana.mostrar_detalle(texto_descanso(descanso.nombre, descanso.duracion_planeada_s))
        self.actualizar_estado()

    def mostrar_cuenta_regresiva(self):
        descanso = self.descansos.actual
        self.cuenta_regresiva.mostrar(descanso.nombre, descanso.duracion_planeada_s)
        self.cuenta_regresiva.actualizar(self.descansos.segundos_restantes(), descanso.duracion_planeada_s)

    def terminar_descanso(self, completado):
        """Al llegar a cero (completado) o con "Terminar antes". Rearma la alerta."""
        if self.descansos.terminar(completado) is None:
            return
        self.reloj_uso.terminar_descanso()
        self.cuenta_regresiva.hide()
        self.ventana.mostrar_detalle(self.texto_detalle)
        self.mostrar_historial()
        self.actualizar_estado()
        if completado:
            self.notificar(AVISO_FIN_DESCANSO)

    def mostrar_historial(self):
        self.pestana_descansos.mostrar_historial(
            self.descansos.historial,
            self.descansos.minutos_del_dia(),
            len(self.descansos.descansos_del_dia()),
        )

    # --- Cada segundo: reloj de uso y cuenta regresiva ---

    def cada_segundo(self):
        self.reloj_uso.tick()
        self.ventana.mostrar_uso(texto_uso(self.reloj_uso.segundos_hoy(), self.reloj_uso.segundos_sesion))

        descanso = self.descansos.actual
        if descanso is None:
            return
        if self.descansos.termino_el_tiempo():
            self.terminar_descanso(completado=True)
            return
        restantes = self.descansos.segundos_restantes()
        self.cuenta_regresiva.actualizar(restantes, descanso.duracion_planeada_s)
        self.ventana.mostrar_detalle(texto_descanso(descanso.nombre, restantes))

    # --- Ajustes ---

    def abrir_ajustes(self):
        autoinicio_antes = self.configuracion["sistema"]["iniciar_con_el_sistema"]
        padre = self.ventana if self.ventana.isVisible() else None
        dialogo = DialogoAjustes(
            self.configuracion, self.constantes, self.puertos_disponibles(), autoinicio.soportado(), padre
        )
        if not dialogo.exec():
            return
        cambio_autoinicio = self.configuracion["sistema"]["iniciar_con_el_sistema"] != autoinicio_antes
        if cambio_autoinicio or rutas.esta_empaquetada():
            self.aplicar_autoinicio(avisar_error=True)
        self.mostrar_detalle("Ajustes guardados. " + NOTA_PARAMETROS)

    def aplicar_autoinicio(self, avisar_error):
        try:
            autoinicio.aplicar(self.configuracion["sistema"]["iniciar_con_el_sistema"])
        except OSError as error:
            texto = f"No se pudo cambiar el inicio con el sistema:\n{error}"
            if avisar_error:
                QMessageBox.warning(None, TITULO_VENTANA, texto)
            else:
                print(texto)

    def puertos_disponibles(self):
        return []

    def abrir_carpeta_datos(self):
        self.carpeta_datos.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.carpeta_datos)))

    # --- Estado que se muestra en la ventana y en la bandeja ---

    def mostrar_detalle(self, texto):
        """Texto bajo el estado. Durante un descanso ahí va la cuenta regresiva."""
        self.texto_detalle = texto
        if not self.descansos.en_descanso():
            self.ventana.mostrar_detalle(texto)

    def estado_visible(self):
        if self.descansos.alerta_pendiente:
            return RIESGO_FATIGA
        if self.descansos.en_descanso():
            return EN_DESCANSO
        return self.estado

    def tipo_icono(self):
        if self.descansos.alerta_pendiente:
            return ICONO_ALERTA
        if self.descansos.en_descanso():
            return ICONO_DESCANSO
        if self.hilo is not None:
            return ICONO_MIDIENDO
        return ICONO_APAGADO

    def actualizar_estado(self):
        estado = self.estado_visible()
        self.ventana.mostrar_estado(estado)
        if self.bandeja is not None:
            self.bandeja.poner_estado(self.tipo_icono(), estado)

    def poner_boton_bandeja(self, texto, activo):
        if self.bandeja is not None:
            self.bandeja.poner_boton_medicion(texto, activo)

    def notificar(self, texto, alerta=False):
        if self.bandeja is not None:
            self.bandeja.notificar(texto, alerta)

    # --- Ventana, bandeja y salida ---

    def mostrar_ventana(self):
        self.ventana.showNormal()
        self.ventana.raise_()
        self.ventana.activateWindow()
        if self.descansos.alerta_pendiente:
            self.dialogo_alerta.traer_al_frente()

    def al_cerrar_ventana(self):
        """El usuario cerró la ventana con la X."""
        if self.bandeja is None:
            self.salir()
        elif not self.aviso_bandeja_mostrado:
            self.aviso_bandeja_mostrado = True
            self.notificar(AVISO_SIGUE_EN_BANDEJA)

    def salir(self):
        # quit() cierra las ventanas (la de alerta lo permite porque no es el usuario
        # quien la cierra) y después llama a cerrar() por la señal aboutToQuit.
        QApplication.quit()

    def cerrar(self):
        """Antes de salir: guarda el descanso en curso, detiene la medición y guarda el reloj."""
        self.temporizador.stop()
        if self.descansos.en_descanso():
            self.descansos.terminar(completado=False)
        if self.hilo is not None:
            self.hilo.detener()
            self.hilo.wait(TIEMPO_MAXIMO_CIERRE_MS)
        self.reloj_uso.terminar_medicion()
        if self.bandeja is not None:
            self.bandeja.hide()


def mostrar_error_fatal(texto):
    """Muestra un error que impide abrir la app (ej. no se encontró el original)."""
    app = QApplication.instance() or QApplication(sys.argv)
    QMessageBox.critical(None, TITULO_VENTANA, texto)
    return app


def ejecutar_ventana(argumentos, original, configuracion, carpeta_base):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(TITULO_VENTANA)
    app.setWindowIcon(crear_icono(ICONO_MIDIENDO))
    # La app sigue en la bandeja aunque no quede ninguna ventana abierta.
    app.setQuitOnLastWindowClosed(False)

    if argumentos.sim:
        configuracion["simulacion"]["activa"] = True

    aplicacion = AplicacionRSI(original, configuracion, carpeta_base, argumentos.umbrales_sim)
    app.aboutToQuit.connect(aplicacion.cerrar)

    # Con --minimizado (al iniciar con el sistema) la app parte solo en la bandeja.
    if not (argumentos.minimizado and aplicacion.bandeja is not None):
        aplicacion.ventana.show()
    return app.exec()
