"""
Ventana de cuenta regresiva del descanso.

Muestra cuánto falta para terminar el descanso y el botón "Terminar antes". Si se
cierra con la X, el descanso sigue (se puede volver a abrir desde la bandeja con
"Tomar descanso" o desde la pestaña Descansos). Al llegar a cero, ui/aplicacion.py
la cierra y avisa con una notificación.

Qué se puede editar aquí: los textos, el tamaño de letra y los colores.
"""

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from uso.reloj_uso import formato_reloj

TITULO_CUENTA_REGRESIVA = "RSI Monitor — Descanso"
TEXTO_TERMINAR_ANTES = "Terminar antes"
TEXTO_PAUSA = "Durante el descanso no se evalúa la fatiga. Aléjese del teclado y del mouse."
TAMANO_LETRA_RELOJ = 40
TAMANO_LETRA_NOMBRE = 14
ANCHO_MINIMO = 380
COLOR_RELOJ = "#2e86c1"


class VentanaCuentaRegresiva(QWidget):
    terminar_antes_pedido = Signal()

    def __init__(self):
        super().__init__(None)
        self.setWindowTitle(TITULO_CUENTA_REGRESIVA)
        self.setWindowFlag(Qt.WindowType.Window)
        self.setMinimumWidth(ANCHO_MINIMO)

        self.etiqueta_nombre = QLabel()
        self.etiqueta_nombre.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fuente_nombre = QFont()
        fuente_nombre.setPointSize(TAMANO_LETRA_NOMBRE)
        fuente_nombre.setBold(True)
        self.etiqueta_nombre.setFont(fuente_nombre)

        self.etiqueta_reloj = QLabel()
        self.etiqueta_reloj.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fuente_reloj = QFont()
        fuente_reloj.setPointSize(TAMANO_LETRA_RELOJ)
        fuente_reloj.setBold(True)
        self.etiqueta_reloj.setFont(fuente_reloj)
        self.etiqueta_reloj.setStyleSheet(f"color: {COLOR_RELOJ};")

        self.barra = QProgressBar()
        self.barra.setTextVisible(False)

        etiqueta_pausa = QLabel(TEXTO_PAUSA)
        etiqueta_pausa.setWordWrap(True)
        etiqueta_pausa.setAlignment(Qt.AlignmentFlag.AlignCenter)

        boton = QPushButton(TEXTO_TERMINAR_ANTES)
        boton.setMinimumHeight(36)
        boton.clicked.connect(self.terminar_antes_pedido.emit)

        disposicion = QVBoxLayout(self)
        disposicion.setContentsMargins(24, 20, 24, 20)
        disposicion.setSpacing(12)
        disposicion.addWidget(self.etiqueta_nombre)
        disposicion.addWidget(self.etiqueta_reloj)
        disposicion.addWidget(self.barra)
        disposicion.addWidget(etiqueta_pausa)
        disposicion.addWidget(boton)

    def mostrar(self, nombre, total_s):
        self.etiqueta_nombre.setText(nombre)
        self.actualizar(total_s, total_s)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def actualizar(self, restantes_s, total_s):
        # Se redondea hacia arriba: 9:59,5 se muestra como 10:00 y el 00:00 dura un instante.
        self.etiqueta_reloj.setText(formato_reloj(math.ceil(restantes_s)))
        self.barra.setMaximum(int(total_s))
        self.barra.setValue(int(total_s - restantes_s))
