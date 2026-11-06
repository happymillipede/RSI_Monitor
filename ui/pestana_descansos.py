"""
Pestaña "Descansos" de la ventana principal y los diálogos para tomar un descanso.

- Botón "Tomar descanso…": abre DialogoTomarDescanso (una plantilla o una duración libre).
- Plantillas: crear, editar y borrar (se guardan en config.json).
- Historial: todos los descansos (datos/descansos.json) y el total de hoy.

La lógica (validar, guardar) está en uso/descansos.py; aquí solo se dibuja.

Qué se puede editar aquí: los textos y las columnas del historial.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from uso.descansos import MINUTOS_MAXIMOS, MINUTOS_MINIMOS, ORIGEN_FATIGA, validar_plantilla

TITULO_DIALOGOS = "RSI Monitor"
MINUTOS_LIBRES_POR_DEFECTO = 5

COLUMNAS_HISTORIAL = ("Inicio", "Fin", "Descanso", "Origen", "Planeado (min)", "Real (min)", "Completado")
TEXTO_ORIGEN = {ORIGEN_FATIGA: "Alerta de fatiga"}  # el resto se muestra como "Manual"
TEXTO_ORIGEN_MANUAL = "Manual"


def texto_plantilla(plantilla):
    return f"{plantilla['nombre']} — {plantilla['duracion_min']:g} min"


def texto_total_del_dia(minutos, cantidad):
    return f"Hoy: {cantidad} descanso(s), {minutos:.1f} min en total"


def crear_spin_minutos(valor):
    spin = QSpinBox()
    spin.setRange(MINUTOS_MINIMOS, MINUTOS_MAXIMOS)
    spin.setSuffix(" min")
    spin.setValue(int(valor))
    return spin


class DialogoPlantilla(QDialog):
    """Pide el nombre y la duración de una plantilla."""

    def __init__(self, padre, titulo, nombre="", minutos=MINUTOS_LIBRES_POR_DEFECTO):
        super().__init__(padre)
        self.setWindowTitle(titulo)
        self.campo_nombre = QLineEdit(nombre)
        self.spin_minutos = crear_spin_minutos(minutos)

        formulario = QFormLayout(self)
        formulario.addRow("Nombre:", self.campo_nombre)
        formulario.addRow("Duración:", self.spin_minutos)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        formulario.addRow(botones)

    def valores(self):
        return self.campo_nombre.text(), self.spin_minutos.value()

    def accept(self):
        try:
            validar_plantilla(*self.valores())
        except ValueError as error:
            QMessageBox.warning(self, TITULO_DIALOGOS, str(error))
            return
        super().accept()


class DialogoTomarDescanso(QDialog):
    """Elegir una plantilla o una duración libre. valores() devuelve (nombre o None, minutos)."""

    def __init__(self, plantillas, padre=None):
        super().__init__(padre)
        self.setWindowTitle("Tomar descanso")
        self.plantillas = plantillas

        self.opcion_plantilla = QRadioButton("Plantilla:")
        self.combo_plantillas = QComboBox()
        for plantilla in plantillas:
            self.combo_plantillas.addItem(texto_plantilla(plantilla))
        self.opcion_libre = QRadioButton("Duración libre:")
        self.spin_minutos = crear_spin_minutos(MINUTOS_LIBRES_POR_DEFECTO)

        if plantillas:
            self.opcion_plantilla.setChecked(True)
        else:
            self.opcion_plantilla.setEnabled(False)
            self.opcion_libre.setChecked(True)
        self.combo_plantillas.activated.connect(lambda: self.opcion_plantilla.setChecked(True))
        self.spin_minutos.valueChanged.connect(lambda: self.opcion_libre.setChecked(True))

        formulario = QFormLayout(self)
        formulario.addRow(self.opcion_plantilla, self.combo_plantillas)
        formulario.addRow(self.opcion_libre, self.spin_minutos)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        botones.addButton("Comenzar", QDialogButtonBox.ButtonRole.AcceptRole)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        formulario.addRow(botones)

    def valores(self):
        if self.opcion_plantilla.isChecked():
            plantilla = self.plantillas[self.combo_plantillas.currentIndex()]
            return plantilla["nombre"], plantilla["duracion_min"]
        return None, self.spin_minutos.value()


class PestanaDescansos(QWidget):
    tomar_descanso_pedido = Signal()

    def __init__(self, plantillas):
        """plantillas: PlantillasDescanso (uso/descansos.py)."""
        super().__init__()
        self.plantillas = plantillas

        boton_tomar = QPushButton("Tomar descanso…")
        boton_tomar.setMinimumHeight(40)
        boton_tomar.clicked.connect(self.tomar_descanso_pedido.emit)

        disposicion = QVBoxLayout(self)
        fila = QHBoxLayout()
        fila.addWidget(boton_tomar)
        fila.addStretch(1)
        disposicion.addLayout(fila)

        columnas = QHBoxLayout()
        columnas.addWidget(self.crear_grupo_plantillas(), stretch=1)
        columnas.addWidget(self.crear_grupo_historial(), stretch=3)
        disposicion.addLayout(columnas, stretch=1)

        self.mostrar_plantillas()

    def crear_grupo_plantillas(self):
        self.lista_plantillas = QListWidget()
        self.lista_plantillas.itemDoubleClicked.connect(self.editar_plantilla)

        botones = QHBoxLayout()
        for texto, accion in (("Agregar", self.agregar_plantilla), ("Editar", self.editar_plantilla), ("Borrar", self.borrar_plantilla)):
            boton = QPushButton(texto)
            boton.clicked.connect(accion)
            botones.addWidget(boton)

        grupo = QGroupBox("Plantillas")
        columna = QVBoxLayout(grupo)
        columna.addWidget(self.lista_plantillas)
        columna.addLayout(botones)
        return grupo

    def crear_grupo_historial(self):
        self.etiqueta_total = QLabel()
        self.tabla = QTableWidget(0, len(COLUMNAS_HISTORIAL))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS_HISTORIAL)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.horizontalHeader().setStretchLastSection(True)

        grupo = QGroupBox("Historial")
        columna = QVBoxLayout(grupo)
        columna.addWidget(self.etiqueta_total)
        columna.addWidget(self.tabla)
        return grupo

    # --- Historial ---

    def mostrar_historial(self, historial, minutos_hoy, cantidad_hoy):
        self.etiqueta_total.setText(texto_total_del_dia(minutos_hoy, cantidad_hoy))
        self.tabla.setRowCount(len(historial))
        # El más reciente arriba
        for fila, descanso in enumerate(reversed(historial)):
            valores = (
                descanso["inicio"].replace("T", " "),
                descanso["fin"].replace("T", " "),
                descanso["nombre"],
                TEXTO_ORIGEN.get(descanso["origen"], TEXTO_ORIGEN_MANUAL),
                f"{descanso['duracion_planeada_min']:g}",
                f"{descanso['duracion_real_min']:.1f}",
                "Sí" if descanso["completado"] else "No",
            )
            for columna, valor in enumerate(valores):
                celda = QTableWidgetItem(valor)
                celda.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tabla.setItem(fila, columna, celda)

    # --- Plantillas ---

    def mostrar_plantillas(self):
        self.lista_plantillas.clear()
        for plantilla in self.plantillas.lista():
            self.lista_plantillas.addItem(texto_plantilla(plantilla))

    def agregar_plantilla(self):
        dialogo = DialogoPlantilla(self, "Nueva plantilla")
        if dialogo.exec():
            self.guardar_plantilla(self.plantillas.agregar, dialogo)

    def editar_plantilla(self):
        indice = self.lista_plantillas.currentRow()
        if indice < 0:
            return
        actual = self.plantillas.lista()[indice]
        dialogo = DialogoPlantilla(self, "Editar plantilla", actual["nombre"], actual["duracion_min"])
        if dialogo.exec():
            self.guardar_plantilla(lambda nombre, minutos: self.plantillas.editar(indice, nombre, minutos), dialogo)

    def guardar_plantilla(self, guardar, dialogo):
        try:
            guardar(*dialogo.valores())
        except ValueError as error:
            QMessageBox.warning(self, TITULO_DIALOGOS, str(error))
        self.mostrar_plantillas()

    def borrar_plantilla(self):
        indice = self.lista_plantillas.currentRow()
        if indice < 0:
            return
        nombre = self.plantillas.lista()[indice]["nombre"]
        respuesta = QMessageBox.question(self, TITULO_DIALOGOS, f'¿Borrar la plantilla "{nombre}"?')
        if respuesta == QMessageBox.StandardButton.Yes:
            self.plantillas.borrar(indice)
            self.mostrar_plantillas()
