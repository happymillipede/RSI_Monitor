"""
Ventana principal de RSI Monitor.

Muestra lo mismo que el código original:
- la tendencia de RMS y la de MDF, con una ventana deslizante de TREND_WINDOW_S segundos;
- el panel de información de actualizar_panel_adquisicion() (líneas 334-375);
y además el estado de la app, el botón Encender/Apagar y el modo de medición.

La ventana solo dibuja y avisa los clics: no procesa la señal. ui/aplicacion.py la
conecta con el hilo de medición.

Qué se puede editar aquí: colores, textos y tamaños de las constantes de abajo.
"""

import math

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from nucleo.adquisicion import BUSCANDO, CALIBRANDO, CONECTANDO, DESCONECTADO, ERROR, MIDIENDO
from uso.reloj_uso import formato_reloj

TITULO_VENTANA = "RSI Monitor"
TAMANO_VENTANA = (1200, 720)

# Mismos colores que el original (matplotlib "tab:orange" y "tab:green")
COLOR_RMS = "#ff7f0e"
COLOR_MDF = "#2ca02c"
TAMANO_PUNTO = 5

MODO_BITALINO = "BITalino"
MODO_SIMULACION = "Simulación"
ESCENARIOS = ("normal", "fatigue_test")
VELOCIDADES_SIMULACION = (1, 10)

TEXTO_ESPERA = "Esperando datos del BITalino..."  # línea 220 del original
LARGO_MAXIMO_TRAMA = 160  # líneas 344-345 del original

# Estados de la app que no vienen de la medición
EN_DESCANSO = "En descanso"
RIESGO_FATIGA = "Riesgo de fatiga: descanso pendiente"

# Color de fondo del indicador según el estado (los que no están usan COLOR_ESTADO_OTRO)
COLORES_ESTADO = {
    DESCONECTADO: "#7f8c8d",
    BUSCANDO: "#d68910",
    CONECTANDO: "#d68910",
    CALIBRANDO: "#2e86c1",
    MIDIENDO: "#239b56",
    EN_DESCANSO: "#17a589",
    ERROR: "#c0392b",
    RIESGO_FATIGA: "#c0392b",
}
COLOR_ESTADO_OTRO = "#7f8c8d"
COLOR_BOTON_ENCENDER = "#239b56"
COLOR_BOTON_APAGAR = "#c0392b"


def texto_panel(info, constantes, parametros, estado):
    """Texto del panel de información. Réplica de actualizar_panel_adquisicion() (líneas 334-375)."""
    if info.muestras_recientes:
        texto_muestras = "\n".join(
            f"  t={tiempo:8.3f} s | EMG={valor}" for tiempo, valor in info.muestras_recientes
        )
    else:
        texto_muestras = "  Todavía no hay muestras."

    texto_trama = repr(info.ultima_trama)
    if len(texto_trama) > LARGO_MAXIMO_TRAMA:
        texto_trama = texto_trama[: LARGO_MAXIMO_TRAMA - 3] + "..."

    periodo = constantes["PERIODO"]
    return (
        "BITALINO — ADQUISICIÓN Y PROCESAMIENTO\n"
        "======================================\n"
        f"Estado: {estado}\n"
        f"Canal configurado: {constantes['CANAL']}\n"
        f"PERIODO: {periodo} s\n"
        f"FS (1 / PERIODO): {1 / periodo:.2f} Hz\n"
        "Duración configurada: indefinida (hasta Apagar)\n"
        f"Tamaño máximo de lectura N: {constantes['N']}\n"
        f"Intervalo de tendencia: {parametros['TREND_INTERVAL_S']} s\n"
        f"Línea base: {parametros['BASELINE_DURATION_S']} s\n"
        f"Persistencia de alerta: {parametros['ALERT_PERSISTENCE_S']} s\n"
        f"Umbral RMS: +{parametros['RMS_INCREASE_THRESHOLD'] * 100:.0f}%\n"
        f"Umbral MDF: -{parametros['MDF_DECREASE_THRESHOLD'] * 100:.0f}%\n\n"
        f"Muestras recibidas: {info.n_medicion}\n"
        f"Último valor EMG (ADC): {info.ultimo_valor_emg}\n"
        f"Último RMS del bloque: {info.ultimo_rms:.3f}\n"
        f"Última MDF del bloque: {info.ultimo_mdf:.3f} Hz\n\n"
        f"Última trama recibida:\n  {texto_trama}\n\n"
        f"Últimas {len(info.muestras_recientes)} muestras:\n"
        f"{texto_muestras}\n\n"
        "Funciones del flujo:\n"
        "device.start() -> inicia BITalino\n"
        "device.read() -> recibe muestras\n"
        "procesar_bloque() -> calcula RMS/MDF\n"
        "cerrar_intervalo() -> resume y guarda CSV\n"
        "device.stop() -> detiene adquisición"
    )


def texto_calibracion(segundos):
    return f"Calibrando línea base ({segundos:g} s): mantén tu postura y ritmo de trabajo normales."


def texto_linea_base(rms, mdf):
    return f"Línea base: RMS = {rms:.3f} ADC · MDF = {mdf:.3f} Hz"


def texto_uso(segundos_hoy, segundos_sesion):
    return f"Uso hoy: {formato_reloj(segundos_hoy)} · Sesión actual: {formato_reloj(segundos_sesion)}"


def texto_descanso(nombre, segundos_restantes):
    return f"{nombre}: quedan {formato_reloj(math.ceil(segundos_restantes))}. Durante el descanso no se evalúa la fatiga."


class GraficoTendencia(pg.PlotWidget):
    """Un gráfico de tendencia que muestra solo los últimos 'ventana_s' segundos."""

    def __init__(self, etiqueta_y, color, ventana_s, etiqueta_x=None):
        super().__init__()
        self.ventana_s = ventana_s
        self.tiempos = []
        self.valores = []

        self.setBackground("w")
        self.showGrid(x=True, y=True, alpha=0.3)
        self.setLabel("left", etiqueta_y)
        if etiqueta_x:
            self.setLabel("bottom", etiqueta_x)
        self.setMouseEnabled(x=False, y=False)
        self.curva = self.plot(
            [], [], pen=pg.mkPen(color, width=2), symbol="o", symbolSize=TAMANO_PUNTO,
            symbolBrush=color, symbolPen=color, connect="finite",
        )
        self.setXRange(0, ventana_s, padding=0)

    def poner_titulo(self, titulo):
        self.setTitle(titulo, color="k")

    def limpiar(self):
        self.tiempos.clear()
        self.valores.clear()
        self.curva.setData([], [])
        self.setXRange(0, self.ventana_s, padding=0)

    def agregar(self, tiempo, valor):
        """Agrega un punto y desplaza la ventana (líneas 307-310 del original)."""
        self.tiempos.append(tiempo)
        self.valores.append(valor if math.isfinite(valor) else float("nan"))

        extremo_derecho = max(self.ventana_s, tiempo)
        extremo_izquierdo = extremo_derecho - self.ventana_s

        # Se guardan solo los puntos visibles, para que la medición pueda durar horas.
        while self.tiempos and self.tiempos[0] < extremo_izquierdo:
            self.tiempos.pop(0)
            self.valores.pop(0)

        self.curva.setData(self.tiempos, self.valores)
        self.setXRange(extremo_izquierdo, extremo_derecho, padding=0)


class VentanaPrincipal(QMainWindow):
    encender_apagar_pedido = Signal()
    modo_cambiado = Signal()
    cerrada_por_usuario = Signal()

    def __init__(self, ventana_tendencia_s):
        super().__init__()
        self.setWindowTitle(TITULO_VENTANA)
        self.resize(*TAMANO_VENTANA)

        self.pestanas = QTabWidget()
        self.pestanas.addTab(self.crear_pestana_medicion(ventana_tendencia_s), "Medición")

        contenido = QWidget()
        disposicion = QVBoxLayout(contenido)
        disposicion.addLayout(self.crear_barra_superior())
        disposicion.addWidget(self.pestanas, stretch=1)
        self.setCentralWidget(contenido)

        self.mostrar_estado(DESCONECTADO)
        self.medicion_detenida()

    # --- Construcción de la interfaz ---

    def crear_barra_superior(self):
        self.etiqueta_estado = QLabel()
        self.etiqueta_estado.setAlignment(Qt.AlignCenter)
        self.etiqueta_estado.setMinimumWidth(320)
        fuente = QFont()
        fuente.setPointSize(13)
        fuente.setBold(True)
        self.etiqueta_estado.setFont(fuente)

        self.etiqueta_detalle = QLabel()
        self.etiqueta_detalle.setWordWrap(True)
        self.etiqueta_uso = QLabel(texto_uso(0, 0))

        columna_estado = QVBoxLayout()
        columna_estado.addWidget(self.etiqueta_estado)
        columna_estado.addWidget(self.etiqueta_detalle)
        columna_estado.addWidget(self.etiqueta_uso)

        self.combo_modo = QComboBox()
        self.combo_modo.addItems([MODO_BITALINO, MODO_SIMULACION])
        self.combo_escenario = QComboBox()
        self.combo_escenario.addItems(ESCENARIOS)
        self.combo_velocidad = QComboBox()
        for velocidad in VELOCIDADES_SIMULACION:
            self.combo_velocidad.addItem(f"×{velocidad}", velocidad)
        for combo in (self.combo_modo, self.combo_escenario, self.combo_velocidad):
            combo.currentIndexChanged.connect(self.al_cambiar_modo)

        columna_modo = QVBoxLayout()
        fila_modo = QHBoxLayout()
        fila_modo.addWidget(QLabel("Modo:"))
        fila_modo.addWidget(self.combo_modo)
        fila_simulacion = QHBoxLayout()
        fila_simulacion.addWidget(QLabel("Escenario:"))
        fila_simulacion.addWidget(self.combo_escenario)
        fila_simulacion.addWidget(QLabel("Velocidad:"))
        fila_simulacion.addWidget(self.combo_velocidad)
        columna_modo.addLayout(fila_modo)
        columna_modo.addLayout(fila_simulacion)

        self.boton_encender = QPushButton()
        self.boton_encender.setMinimumSize(200, 64)
        fuente_boton = QFont()
        fuente_boton.setPointSize(16)
        fuente_boton.setBold(True)
        self.boton_encender.setFont(fuente_boton)
        self.boton_encender.clicked.connect(self.encender_apagar_pedido.emit)

        barra = QHBoxLayout()
        barra.addLayout(columna_estado, stretch=1)
        barra.addLayout(columna_modo)
        barra.addWidget(self.boton_encender)
        return barra

    def crear_pestana_medicion(self, ventana_tendencia_s):
        self.grafico_rms = GraficoTendencia("RMS (ADC)", COLOR_RMS, ventana_tendencia_s)
        self.grafico_mdf = GraficoTendencia(
            "Frecuencia mediana (Hz)", COLOR_MDF, ventana_tendencia_s, etiqueta_x="Tiempo (s)"
        )
        self.grafico_mdf.setXLink(self.grafico_rms)

        graficos = QWidget()
        columna = QVBoxLayout(graficos)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.addWidget(self.grafico_rms)
        columna.addWidget(self.grafico_mdf)

        self.panel = QPlainTextEdit()
        self.panel.setReadOnly(True)
        fuente = QFont("Monospace")
        fuente.setStyleHint(QFont.TypeWriter)
        fuente.setPointSize(9)
        self.panel.setFont(fuente)
        self.panel.setPlainText(TEXTO_ESPERA)

        # Proporción 2.2 : 1 como la rejilla del original (línea 193)
        divisor = QSplitter()
        divisor.addWidget(graficos)
        divisor.addWidget(self.panel)
        divisor.setSizes([770, 350])
        return divisor

    # --- Lo que el coordinador le pide a la ventana ---

    def mostrar_estado(self, texto):
        color = COLORES_ESTADO.get(texto, COLOR_ESTADO_OTRO)
        self.etiqueta_estado.setText(texto)
        self.etiqueta_estado.setStyleSheet(
            f"background-color: {color}; color: white; border-radius: 6px; padding: 8px;"
        )

    def mostrar_detalle(self, texto):
        self.etiqueta_detalle.setText(texto)

    def mostrar_uso(self, texto):
        self.etiqueta_uso.setText(texto)

    def agregar_pestana(self, widget, titulo):
        self.pestanas.addTab(widget, titulo)

    def mostrar_panel(self, texto):
        self.panel.setPlainText(texto)

    def medicion_iniciada(self, intervalo_tendencia_s):
        """Limpia los gráficos y deja el botón en "Apagar"."""
        self.grafico_rms.poner_titulo(f"Tendencia de RMS (promedio cada {intervalo_tendencia_s:g} s)")
        self.grafico_mdf.poner_titulo(f"Tendencia de MDF (mediana cada {intervalo_tendencia_s:g} s)")
        self.grafico_rms.limpiar()
        self.grafico_mdf.limpiar()
        self.panel.setPlainText(TEXTO_ESPERA)
        self.poner_boton("Apagar", COLOR_BOTON_APAGAR, activo=True)
        self.activar_selector_modo(False)

    def apagando(self):
        self.poner_boton("Apagando…", COLOR_BOTON_APAGAR, activo=False)

    def medicion_detenida(self):
        self.poner_boton("Encender", COLOR_BOTON_ENCENDER, activo=True)
        self.activar_selector_modo(True)

    def agregar_intervalo(self, resumen):
        self.grafico_rms.agregar(resumen.tiempo, resumen.rms)
        self.grafico_mdf.agregar(resumen.tiempo, resumen.mdf)

    # --- Modo de medición ---

    def poner_modo(self, simulacion, escenario, velocidad):
        for combo in (self.combo_modo, self.combo_escenario, self.combo_velocidad):
            combo.blockSignals(True)
        self.combo_modo.setCurrentText(MODO_SIMULACION if simulacion else MODO_BITALINO)
        self.combo_escenario.setCurrentText(escenario)
        indice = self.combo_velocidad.findData(velocidad)
        self.combo_velocidad.setCurrentIndex(max(indice, 0))
        for combo in (self.combo_modo, self.combo_escenario, self.combo_velocidad):
            combo.blockSignals(False)
        self.activar_selector_modo(True)

    def modo_simulacion(self):
        return self.combo_modo.currentText() == MODO_SIMULACION

    def escenario(self):
        return self.combo_escenario.currentText()

    def velocidad(self):
        return self.combo_velocidad.currentData()

    def al_cambiar_modo(self):
        self.activar_selector_modo(True)
        self.modo_cambiado.emit()

    def activar_selector_modo(self, activo):
        self.combo_modo.setEnabled(activo)
        simulacion = activo and self.modo_simulacion()
        self.combo_escenario.setEnabled(simulacion)
        self.combo_velocidad.setEnabled(simulacion)

    def closeEvent(self, evento):
        # Cerrar la ventana solo la esconde (no tiene WA_DeleteOnClose). Si fue el usuario
        # (la X), se avisa al coordinador, que deja la app en la bandeja.
        evento.accept()
        if evento.spontaneous():
            self.cerrada_por_usuario.emit()

    def poner_boton(self, texto, color, activo):
        self.boton_encender.setText(texto)
        self.boton_encender.setEnabled(activo)
        self.boton_encender.setStyleSheet(
            f"QPushButton {{ background-color: {color}; color: white; border-radius: 8px; }}"
            "QPushButton:disabled { background-color: #95a5a6; }"
        )
