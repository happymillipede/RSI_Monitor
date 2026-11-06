"""
Estado en memoria de la app: lo que el navegador necesita para dibujar la pantalla.

- Datos de la medición y de la conexión.
- Búferes circulares (collections.deque con tamaño máximo): los puntos de tendencia
  de la sesión y los últimos bloques. Cuando se llenan, se descarta lo más antiguo.
  El CSV en datos/ siempre guarda todos los puntos.

La alerta pendiente y el descanso en curso viven en uso/descansos.py
(GestorDescansos), y el reloj de uso en uso/reloj_uso.py.

Qué se puede editar aquí: nada en particular. Los tamaños de los búferes se cambian
en config.json (sección "memoria").
"""

from collections import deque

from app.nucleo.adquisicion import CONECTANDO, DESCONECTADO


class EstadoApp:
    def __init__(self, max_puntos_tendencia, max_bloques):
        self.tendencia = deque(maxlen=max_puntos_tendencia)  # PuntoTendencia
        self.bloques = deque(maxlen=max_bloques)  # Bloque

        # Medición
        self.encendida = False
        self.modo = None  # "real" o "simulacion"
        self.escenario = None
        self.velocidad = None
        self.umbrales_sim = False
        self.estado_medicion = DESCONECTADO
        self.ruta_csv = None
        self.parametros = None  # parámetros de detección de la sesión
        self.linea_base = None  # (RMS, MDF) cuando termina la calibración

        # Conexión
        self.estado_conexion = "Desconectado"
        self.puerto = None
        self.version = None
        self.detalle_conexion = ""

    def nueva_sesion(self, modo, escenario, velocidad, umbrales_sim, parametros, ruta_csv):
        """Al encender: se vacían los búferes y se anotan los datos de la sesión."""
        self.tendencia.clear()
        self.bloques.clear()
        self.encendida = True
        self.modo = modo
        self.escenario = escenario
        self.velocidad = velocidad
        self.umbrales_sim = umbrales_sim
        self.parametros = parametros
        self.ruta_csv = ruta_csv
        self.estado_medicion = CONECTANDO
        self.linea_base = None
        self.puerto = None
        self.version = None

    def ultimo_bloque(self):
        return self.bloques[-1] if self.bloques else None
