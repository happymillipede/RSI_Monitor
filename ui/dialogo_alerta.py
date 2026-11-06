"""
Ventana de alerta de fatiga.

Aparece cuando la regla del original detecta un patrón de fatiga sostenido:
- dice "Riesgo de fatiga muscular, descanse X minutos" y, en letra chica, que no es
  un diagnóstico médico;
- tiene un solo botón, "Aceptar", que inicia el descanso;
- queda siempre encima de las demás ventanas y no se puede cerrar con la X, con
  Escape ni con Alt+F4, ni minimizar. Solo se cierra con Aceptar o al salir de la app.

Qué se puede editar aquí: los textos, el tamaño de letra y los colores de abajo.
"""

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QCursor, QFont, QGuiApplication
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from nucleo.regla_fatiga import ACLARACION_MEDICA

TEXTO_ALERTA = "Riesgo de fatiga muscular, descanse {minutos} minutos"
TITULO_ALERTA = "RSI Monitor — Riesgo de fatiga"
TEXTO_BOTON_ACEPTAR = "Aceptar"

TAMANO_LETRA_ALERTA = 18
TAMANO_LETRA_ACLARACION = 9
ANCHO_MINIMO = 480
COLOR_ALERTA = "#c0392b"
COLOR_ACLARACION = "#7f8c8d"
COLOR_BOTON = "#239b56"


def texto_alerta(minutos):
    return TEXTO_ALERTA.format(minutos=minutos)


class DialogoAlerta(QDialog):
    """Al apretar Aceptar emite la señal 'accepted' de QDialog."""

    def __init__(self):
        # Sin ventana "padre": así aparece aunque la ventana principal esté en la bandeja.
        super().__init__(None)
        self.setWindowTitle(TITULO_ALERTA)
        # Solo barra de título: sin botones de cerrar, minimizar ni maximizar.
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(ANCHO_MINIMO)

        self.etiqueta_mensaje = QLabel()
        self.etiqueta_mensaje.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.etiqueta_mensaje.setWordWrap(True)
        fuente = QFont()
        fuente.setPointSize(TAMANO_LETRA_ALERTA)
        fuente.setBold(True)
        self.etiqueta_mensaje.setFont(fuente)
        self.etiqueta_mensaje.setStyleSheet(f"color: {COLOR_ALERTA};")

        etiqueta_aclaracion = QLabel(ACLARACION_MEDICA)
        etiqueta_aclaracion.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fuente_chica = QFont()
        fuente_chica.setPointSize(TAMANO_LETRA_ACLARACION)
        etiqueta_aclaracion.setFont(fuente_chica)
        etiqueta_aclaracion.setStyleSheet(f"color: {COLOR_ACLARACION};")

        boton = QPushButton(TEXTO_BOTON_ACEPTAR)
        boton.setMinimumHeight(44)
        boton.setStyleSheet(
            f"background-color: {COLOR_BOTON}; color: white; font-weight: bold; border-radius: 6px;"
        )
        boton.setDefault(True)
        boton.clicked.connect(self.accept)

        disposicion = QVBoxLayout(self)
        disposicion.setContentsMargins(28, 24, 28, 20)
        disposicion.setSpacing(16)
        disposicion.addWidget(self.etiqueta_mensaje)
        disposicion.addWidget(boton)
        disposicion.addWidget(etiqueta_aclaracion)

    def mostrar(self, minutos):
        self.etiqueta_mensaje.setText(texto_alerta(minutos))
        self.adjustSize()
        self.centrar()
        self.traer_al_frente()

    def traer_al_frente(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def centrar(self):
        """La pone al centro de la pantalla donde está el mouse."""
        pantalla = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if pantalla is None:
            return
        area = pantalla.availableGeometry()
        self.move(area.center() - self.rect().center())

    # --- Lo que impide cerrarla o minimizarla ---

    def reject(self):
        """Escape llama a reject(): no hace nada, la alerta solo se cierra con Aceptar."""

    def closeEvent(self, evento):
        # Si el usuario la cierra (X, Alt+F4), el evento es "espontáneo" y se ignora.
        # Si la app se está cerrando (menú Salir, Cmd+Q, apagar el equipo), se acepta.
        if evento.spontaneous():
            evento.ignore()
        else:
            evento.accept()

    def changeEvent(self, evento):
        # Si el sistema la minimiza igual, se vuelve a mostrar enseguida.
        if evento.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            QTimer.singleShot(0, self.traer_al_frente)
        super().changeEvent(evento)
