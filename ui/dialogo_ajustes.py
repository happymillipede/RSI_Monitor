"""
Ventana de ajustes. Todo se guarda en config.json; el original no se toca.

- Detección de fatiga: los 5 parámetros del original. Al lado de cada uno se ve el
  valor del original y el botón "Restaurar". Si un valor queda igual al del original
  se guarda como null, para seguir los cambios que se hagan en el original.
- Simulación: usar o no los umbrales SIM_* del original.
- Conexión: puerto manual (vacío = buscar el BITalino solo).
- Descansos: minutos del descanso por fatiga.
- Sistema: iniciar con el sistema.

Qué se puede editar aquí: los textos de DESCRIPCION_PARAMETROS y los decimales.
"""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from nucleo.configuracion import LIMITES_PARAMETROS, PARAMETROS_DETECCION
from ui.pestana_descansos import crear_spin_minutos

# Nombre en la ventana y unidad de cada parámetro del original
DESCRIPCION_PARAMETROS = {
    "TREND_INTERVAL_S": ("Intervalo de tendencia", "s"),
    "BASELINE_DURATION_S": ("Duración de la línea base", "s"),
    "ALERT_PERSISTENCE_S": ("Persistencia del patrón para alertar", "s"),
    "RMS_INCREASE_THRESHOLD": ("Aumento de RMS sobre la línea base", "%"),
    "MDF_DECREASE_THRESHOLD": ("Disminución de MDF bajo la línea base", "%"),
}
PORCENTAJE = 100  # los umbrales se guardan como fracción (0.20) y se muestran en % (20)
DECIMALES = 2
TEXTO_AUTOMATICO = "Automático (buscar el BITalino)"
NOTA_PARAMETROS = "Los cambios de detección se aplican la próxima vez que encienda la medición."


def escala(nombre):
    return PORCENTAJE if DESCRIPCION_PARAMETROS[nombre][1] == "%" else 1


class DialogoAjustes(QDialog):
    def __init__(self, configuracion, constantes, puertos=(), autoinicio_soportado=True, padre=None):
        """puertos: puertos serie encontrados, para elegir uno a mano."""
        super().__init__(padre)
        self.setWindowTitle("Ajustes de RSI Monitor")
        self.configuracion = configuracion
        self.constantes = constantes

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(self.crear_grupo_deteccion())
        disposicion.addWidget(self.crear_grupo_simulacion())
        disposicion.addWidget(self.crear_grupo_conexion(puertos))
        disposicion.addWidget(self.crear_grupo_otros(autoinicio_soportado))

        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        botones.addButton("Guardar", QDialogButtonBox.ButtonRole.AcceptRole)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        disposicion.addWidget(botones)

    # --- Grupos ---

    def crear_grupo_deteccion(self):
        grupo = QGroupBox("Detección de fatiga")
        rejilla = QGridLayout(grupo)
        guardados = self.configuracion["parametros_deteccion"]
        self.spins = {}

        for fila, nombre in enumerate(PARAMETROS_DETECCION):
            texto, unidad = DESCRIPCION_PARAMETROS[nombre]
            factor = escala(nombre)
            minimo, maximo = LIMITES_PARAMETROS[nombre]
            valor_original = self.constantes[nombre] * factor

            spin = QDoubleSpinBox()
            spin.setDecimals(DECIMALES)
            spin.setRange(minimo * factor, maximo * factor)
            spin.setSuffix(f" {unidad}")
            guardado = guardados.get(nombre)
            spin.setValue(valor_original if guardado is None else guardado * factor)
            self.spins[nombre] = spin

            boton = QPushButton("Restaurar")
            boton.setToolTip("Volver al valor de Código_Bitalino_Python.py")
            boton.clicked.connect(lambda _=False, s=spin, v=valor_original: s.setValue(v))

            etiqueta = QLabel(f"{texto} ({nombre}):")
            rejilla.addWidget(etiqueta, fila, 0)
            rejilla.addWidget(spin, fila, 1)
            rejilla.addWidget(QLabel(f"Original: {valor_original:g} {unidad}"), fila, 2)
            rejilla.addWidget(boton, fila, 3)

        nota = QLabel(NOTA_PARAMETROS)
        nota.setWordWrap(True)
        rejilla.addWidget(nota, len(PARAMETROS_DETECCION), 0, 1, 4)
        return grupo

    def crear_grupo_simulacion(self):
        grupo = QGroupBox("Simulación")
        columna = QVBoxLayout(grupo)
        self.casilla_umbrales_sim = QCheckBox("Usar los umbrales SIM_* del original en modo Simulación")
        self.casilla_umbrales_sim.setChecked(self.configuracion["simulacion"]["usar_umbrales_sim"])
        valores_sim = ", ".join(f"SIM_{nombre} = {self.constantes['SIM_' + nombre]:g}" for nombre in PARAMETROS_DETECCION)
        detalle = QLabel(valores_sim)
        detalle.setWordWrap(True)
        columna.addWidget(self.casilla_umbrales_sim)
        columna.addWidget(detalle)
        return grupo

    def crear_grupo_conexion(self, puertos):
        grupo = QGroupBox("Conexión con el BITalino")
        formulario = QFormLayout(grupo)
        conexion = self.configuracion["conexion"]

        self.combo_puerto = QComboBox()
        self.combo_puerto.setEditable(True)
        self.combo_puerto.addItem(TEXTO_AUTOMATICO)
        self.combo_puerto.addItems(list(puertos))
        if conexion["puerto_manual"]:
            self.combo_puerto.setCurrentText(conexion["puerto_manual"])
        formulario.addRow("Puerto:", self.combo_puerto)
        ultimo = conexion["ultimo_puerto"] or "ninguno todavía"
        formulario.addRow("Último puerto que funcionó:", QLabel(ultimo))
        return grupo

    def crear_grupo_otros(self, autoinicio_soportado):
        grupo = QGroupBox("Descansos y sistema")
        formulario = QFormLayout(grupo)
        self.spin_descanso = crear_spin_minutos(self.configuracion["descansos"]["duracion_fatiga_min"])
        formulario.addRow("Descanso por fatiga:", self.spin_descanso)

        self.casilla_autoinicio = QCheckBox("Iniciar RSI Monitor con el sistema (queda en la bandeja)")
        self.casilla_autoinicio.setChecked(self.configuracion["sistema"]["iniciar_con_el_sistema"])
        if not autoinicio_soportado:
            self.casilla_autoinicio.setEnabled(False)
            self.casilla_autoinicio.setToolTip("Solo en Windows y macOS.")
        formulario.addRow(self.casilla_autoinicio)
        return grupo

    # --- Guardar ---

    def puerto_elegido(self):
        texto = self.combo_puerto.currentText().strip()
        return None if texto in ("", TEXTO_AUTOMATICO) else texto

    def accept(self):
        for nombre, spin in self.spins.items():
            self.configuracion.poner_parametro(nombre, spin.value() / escala(nombre), self.constantes)
        self.configuracion["simulacion"]["usar_umbrales_sim"] = self.casilla_umbrales_sim.isChecked()
        self.configuracion["conexion"]["puerto_manual"] = self.puerto_elegido()
        self.configuracion["descansos"]["duracion_fatiga_min"] = self.spin_descanso.value()
        self.configuracion["sistema"]["iniciar_con_el_sistema"] = self.casilla_autoinicio.isChecked()
        self.configuracion.guardar()
        super().accept()
