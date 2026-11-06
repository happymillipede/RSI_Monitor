"""
Coordinador de la app con ventana: conecta el hilo de medición con la ventana
principal, la ventana de alerta y el ícono de la bandeja.

Aquí se decide qué hacer cuando el usuario aprieta algo y qué mostrar cuando el hilo
avisa algo. No hay procesamiento de señal: eso está en nucleo/.

Qué se puede editar aquí: TIEMPO_MAXIMO_CIERRE_MS y los textos de los avisos.
"""

import sys

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QMessageBox

from nucleo import rutas
from nucleo.adquisicion import CALIBRANDO, DESCONECTADO, ERROR, HiloAdquisicion, SesionMedicion, prefijo_csv
from nucleo.simulador import DispositivoSimulado
from ui.bandeja import ICONO_ALERTA, ICONO_APAGADO, ICONO_MIDIENDO, Bandeja, crear_icono
from ui.dialogo_alerta import DialogoAlerta, texto_alerta
from ui.ventana_principal import (
    RIESGO_FATIGA,
    TITULO_VENTANA,
    VentanaPrincipal,
    texto_calibracion,
    texto_linea_base,
    texto_panel,
)

# Al salir se espera a que el hilo cierre el dispositivo como máximo este tiempo.
TIEMPO_MAXIMO_CIERRE_MS = 5000

AVISO_SIGUE_EN_BANDEJA = (
    "RSI Monitor sigue funcionando en la bandeja. Para cerrarlo use Salir en el menú del ícono."
)


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
        self.alerta_pendiente = False
        self.aviso_bandeja_mostrado = False

        self.ventana = VentanaPrincipal(self.constantes["TREND_WINDOW_S"])
        simulacion = configuracion["simulacion"]
        self.ventana.poner_modo(
            simulacion["activa"],
            configuracion.escenario_simulacion(self.constantes),
            simulacion["velocidad"],
        )
        self.ventana.encender_apagar_pedido.connect(self.alternar_medicion)
        self.ventana.modo_cambiado.connect(self.guardar_modo)
        self.ventana.cerrada_por_usuario.connect(self.al_cerrar_ventana)

        self.dialogo_alerta = DialogoAlerta()
        self.dialogo_alerta.accepted.connect(self.aceptar_alerta)

        # Si el sistema no tiene bandeja (pasa en algunos escritorios Linux), la app
        # funciona igual, pero cerrar la ventana cierra la app.
        self.bandeja = None
        if Bandeja.disponible():
            self.bandeja = Bandeja()
            self.bandeja.mostrar_pedido.connect(self.mostrar_ventana)
            self.bandeja.encender_apagar_pedido.connect(self.alternar_medicion)
            self.bandeja.descanso_pedido.connect(self.tomar_descanso)
            self.bandeja.salir_pedido.connect(self.salir)
            self.bandeja.show()

        self.actualizar_estado()

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

        self.ventana.medicion_iniciada(self.parametros["TREND_INTERVAL_S"])
        self.ventana.mostrar_detalle(f"Guardando en {sesion.ruta_csv.name}")
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
            self.ventana.mostrar_detalle(texto_calibracion(self.parametros["BASELINE_DURATION_S"]))
        elif estado == ERROR:
            self.ventana.mostrar_detalle(detalle)

    def al_procesar_bloque(self, info):
        self.ventana.mostrar_panel(texto_panel(info, self.constantes, self.parametros, self.estado))

    def al_cerrar_intervalo(self, resumen, linea_base):
        self.ventana.agregar_intervalo(resumen)
        if linea_base is not None:
            self.ventana.mostrar_detalle(texto_linea_base(*linea_base))

    # --- Alerta de fatiga ---

    def al_detectar_fatiga(self, resumen):
        if self.alerta_pendiente:  # ya hay una alerta esperando Aceptar: no se repite
            return
        self.alerta_pendiente = True
        minutos = self.configuracion["descansos"]["duracion_fatiga_min"]
        self.dialogo_alerta.mostrar(minutos)
        self.notificar(texto_alerta(minutos), alerta=True)
        self.actualizar_estado()

    def aceptar_alerta(self):
        self.alerta_pendiente = False
        self.actualizar_estado()

    # --- Estado que se muestra en la ventana y en la bandeja ---

    def estado_visible(self):
        if self.alerta_pendiente:
            return RIESGO_FATIGA
        return self.estado

    def tipo_icono(self):
        if self.alerta_pendiente:
            return ICONO_ALERTA
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
        if self.alerta_pendiente:
            self.dialogo_alerta.traer_al_frente()

    def tomar_descanso(self):
        # Mientras hay una alerta pendiente, el descanso empieza con su botón Aceptar.
        if self.alerta_pendiente:
            self.dialogo_alerta.traer_al_frente()
            return
        self.mostrar_ventana()
        self.ventana.mostrar_detalle("Los descansos manuales se agregan en la Fase 4.")

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
        """Detiene la medición antes de salir (cierra el último intervalo y el dispositivo)."""
        if self.hilo is not None:
            self.hilo.detener()
            self.hilo.wait(TIEMPO_MAXIMO_CIERRE_MS)
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
