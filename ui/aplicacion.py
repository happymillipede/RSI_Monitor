"""
Coordinador de la app con ventana: conecta el hilo de medición con la ventana.
(En las fases siguientes también la bandeja, la alerta, los descansos y el reloj de uso.)

Aquí se decide qué hacer cuando el usuario aprieta Encender/Apagar y qué mostrar
cuando el hilo avisa algo. No hay procesamiento de señal: eso está en nucleo/.

Qué se puede editar aquí: TIEMPO_MAXIMO_CIERRE_MS.
"""

import sys

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication, QMessageBox

from nucleo import rutas
from nucleo.adquisicion import CALIBRANDO, ERROR, HiloAdquisicion, SesionMedicion, prefijo_csv
from nucleo.simulador import DispositivoSimulado
from ui.ventana_principal import (
    TITULO_VENTANA,
    VentanaPrincipal,
    texto_calibracion,
    texto_linea_base,
    texto_panel,
)

# Al salir se espera a que el hilo cierre el dispositivo como máximo este tiempo.
TIEMPO_MAXIMO_CIERRE_MS = 5000


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
        self.estado = None

        self.ventana = VentanaPrincipal(self.constantes["TREND_WINDOW_S"])
        simulacion = configuracion["simulacion"]
        self.ventana.poner_modo(
            simulacion["activa"],
            configuracion.escenario_simulacion(self.constantes),
            simulacion["velocidad"],
        )
        self.ventana.encender_apagar_pedido.connect(self.alternar_medicion)
        self.ventana.modo_cambiado.connect(self.guardar_modo)

    # --- Encender / Apagar ---

    def alternar_medicion(self):
        if self.hilo is None:
            self.encender()
        else:
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
        self.hilo.finished.connect(self.al_terminar_hilo)

        self.ventana.medicion_iniciada(self.parametros["TREND_INTERVAL_S"])
        self.ventana.mostrar_detalle(f"Guardando en {sesion.ruta_csv.name}")
        self.hilo.start()

    def apagar(self):
        # No se espera aquí al hilo: la ventana sigue respondiendo y
        # al_terminar_hilo() se llama cuando el hilo cierra el dispositivo.
        self.hilo.detener()
        self.ventana.apagando()

    def al_terminar_hilo(self):
        # La señal "finished" llega justo antes de que el hilo termine del todo:
        # se espera ese instante (milisegundos) antes de soltarlo.
        self.hilo.wait()
        self.hilo = None
        self.ventana.medicion_detenida()

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
        self.ventana.mostrar_estado(estado)
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

    # --- Salida ---

    def cerrar(self):
        """Detiene la medición antes de salir (cierra el último intervalo y el dispositivo)."""
        if self.hilo is not None:
            self.hilo.detener()
            self.hilo.wait(TIEMPO_MAXIMO_CIERRE_MS)


def mostrar_error_fatal(texto):
    """Muestra un error que impide abrir la app (ej. no se encontró el original)."""
    app = QApplication.instance() or QApplication(sys.argv)
    QMessageBox.critical(None, TITULO_VENTANA, texto)
    return app


def ejecutar_ventana(argumentos, original, configuracion, carpeta_base):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(TITULO_VENTANA)

    if argumentos.sim:
        configuracion["simulacion"]["activa"] = True

    aplicacion = AplicacionRSI(original, configuracion, carpeta_base, argumentos.umbrales_sim)
    app.aboutToQuit.connect(aplicacion.cerrar)
    aplicacion.ventana.show()
    return app.exec()
