"""
Ícono de RSI Monitor en la bandeja del sistema (junto al reloj en Windows, en la
barra de menús en macOS) y sus notificaciones.

- El ícono cambia de color según lo que pasa: apagado (gris), midiendo (verde),
  riesgo de fatiga (rojo) y en descanso (azul). Se dibuja con QPainter, sin archivos.
- Menú: Mostrar, Encender/Apagar, Tomar descanso, Salir.
- Al cerrar la ventana principal, la app sigue funcionando aquí.

Qué se puede editar aquí: los colores, los textos del menú y la duración de las notificaciones.
"""

import sys

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

TITULO_BANDEJA = "RSI Monitor"

# Tipos de ícono
ICONO_APAGADO = "apagado"
ICONO_MIDIENDO = "midiendo"
ICONO_ALERTA = "alerta"
ICONO_DESCANSO = "descanso"

COLORES_ICONO = {
    ICONO_APAGADO: "#7f8c8d",
    ICONO_MIDIENDO: "#239b56",
    ICONO_ALERTA: "#c0392b",
    ICONO_DESCANSO: "#2e86c1",
}
TAMANOS_ICONO = (16, 24, 32, 48, 64, 128, 256)  # en píxeles

# Dibujo, como fracción del lado del ícono
MARGEN = 0.04
GROSOR_TRAZO = 0.09
# Onda de EMG (apagado y midiendo)
PUNTOS_ONDA = ((0.18, 0.5), (0.34, 0.5), (0.43, 0.27), (0.53, 0.73), (0.61, 0.38), (0.67, 0.5), (0.82, 0.5))
# Signo de exclamación (alerta)
EXCLAMACION_ARRIBA = 0.22
EXCLAMACION_ABAJO = 0.58
EXCLAMACION_PUNTO = 0.75
RADIO_PUNTO = 0.065
# Barras de pausa (descanso)
PAUSA_X = (0.39, 0.61)
PAUSA_ARRIBA = 0.3
PAUSA_ABAJO = 0.7

DURACION_NOTIFICACION_MS = 10000

TEXTO_MOSTRAR = "Mostrar"
TEXTO_TOMAR_DESCANSO = "Tomar descanso"
TEXTO_SALIR = "Salir"


def dibujar_icono(tipo, lado):
    """Dibuja un ícono redondo de 'lado' píxeles. Devuelve un QPixmap."""
    imagen = QPixmap(lado, lado)
    imagen.fill(Qt.GlobalColor.transparent)

    pintor = QPainter(imagen)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)

    margen = MARGEN * lado
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(QColor(COLORES_ICONO[tipo]))
    pintor.drawEllipse(QRectF(margen, margen, lado - 2 * margen, lado - 2 * margen))

    trazo = QPen(QColor("white"), GROSOR_TRAZO * lado)
    trazo.setCapStyle(Qt.PenCapStyle.RoundCap)
    trazo.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pintor.setPen(trazo)
    pintor.setBrush(Qt.BrushStyle.NoBrush)

    def punto(x, y):
        return QPointF(x * lado, y * lado)

    if tipo == ICONO_ALERTA:
        pintor.drawLine(punto(0.5, EXCLAMACION_ARRIBA), punto(0.5, EXCLAMACION_ABAJO))
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor("white"))
        pintor.drawEllipse(punto(0.5, EXCLAMACION_PUNTO), RADIO_PUNTO * lado, RADIO_PUNTO * lado)
    elif tipo == ICONO_DESCANSO:
        for x in PAUSA_X:
            pintor.drawLine(punto(x, PAUSA_ARRIBA), punto(x, PAUSA_ABAJO))
    else:
        pintor.drawPolyline([punto(x, y) for x, y in PUNTOS_ONDA])

    pintor.end()
    return imagen


_iconos = {}


def crear_icono(tipo):
    """QIcon con el dibujo en varios tamaños (se dibuja una sola vez por tipo)."""
    if tipo not in _iconos:
        icono = QIcon()
        for lado in TAMANOS_ICONO:
            icono.addPixmap(dibujar_icono(tipo, lado))
        _iconos[tipo] = icono
    return _iconos[tipo]


class Bandeja(QSystemTrayIcon):
    mostrar_pedido = Signal()
    encender_apagar_pedido = Signal()
    descanso_pedido = Signal()
    salir_pedido = Signal()

    def __init__(self):
        super().__init__(crear_icono(ICONO_APAGADO))
        self.setToolTip(TITULO_BANDEJA)

        self.menu = QMenu()
        self.menu.addAction(TEXTO_MOSTRAR, self.mostrar_pedido.emit)
        self.accion_encender = self.menu.addAction("Encender", self.encender_apagar_pedido.emit)
        self.menu.addAction(TEXTO_TOMAR_DESCANSO, self.descanso_pedido.emit)
        self.menu.addSeparator()
        self.menu.addAction(TEXTO_SALIR, self.salir_pedido.emit)
        self.setContextMenu(self.menu)

        self.activated.connect(self.al_activar)

    @staticmethod
    def disponible():
        return QSystemTrayIcon.isSystemTrayAvailable()

    def al_activar(self, razon):
        # Clic en el ícono: muestra la ventana. En macOS el clic abre el menú, así que ahí no.
        clic = razon in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick)
        if clic and sys.platform != "darwin":
            self.mostrar_pedido.emit()

    def poner_estado(self, tipo_icono, texto_estado):
        self.setIcon(crear_icono(tipo_icono))
        self.setToolTip(f"{TITULO_BANDEJA} — {texto_estado}")

    def poner_boton_medicion(self, texto, activo):
        self.accion_encender.setText(texto)
        self.accion_encender.setEnabled(activo)

    def notificar(self, texto, alerta=False):
        tipo = QSystemTrayIcon.MessageIcon.Warning if alerta else QSystemTrayIcon.MessageIcon.Information
        self.showMessage(TITULO_BANDEJA, texto, tipo, DURACION_NOTIFICACION_MS)
