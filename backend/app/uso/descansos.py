"""
Descansos: el que viene de una alerta de fatiga, los que el usuario toma por su
cuenta, el historial y las plantillas.

Flujo de la alerta:
    alerta -> pendiente -> Aceptar -> descanso -> fin del descanso -> la alerta se rearma
- Mientras la alerta está pendiente no se abre otra.
- Durante cualquier descanso no se evalúa la fatiga (la regla queda en pausa).
- La línea base se mantiene.

- GestorDescansos: el descanso actual y el historial.
- PlantillasDescanso: las plantillas ("Café, 15 min").
Los dos se guardan en datos/descansos.json (secciones "historial" y "plantillas").

"medicion" es el objeto que recibe las órdenes pausar_alertas() y rearmar_alerta():
la SesionMedicion en curso (o None si la medición está apagada).

Qué se puede editar aquí: los nombres por defecto y los límites de duración.
"""

from dataclasses import dataclass
from datetime import datetime

ORIGEN_FATIGA = "fatiga"
ORIGEN_MANUAL = "manual"
NOMBRE_DESCANSO_FATIGA = "Descanso por fatiga"
NOMBRE_DESCANSO_LIBRE = "Descanso libre"

MINUTOS_MINIMOS = 1
MINUTOS_MAXIMOS = 240
SEGUNDOS_POR_MINUTO = 60
FORMATO_FECHA = "%Y-%m-%dT%H:%M:%S"
DECIMALES_MINUTOS = 2


def validar_minutos(minutos):
    if not MINUTOS_MINIMOS <= minutos <= MINUTOS_MAXIMOS:
        raise ValueError(f"La duración debe estar entre {MINUTOS_MINIMOS} y {MINUTOS_MAXIMOS} minutos.")


@dataclass
class Descanso:
    nombre: str
    origen: str  # ORIGEN_FATIGA u ORIGEN_MANUAL
    inicio: datetime
    duracion_planeada_s: float
    fin: datetime = None
    completado: bool = False

    def como_diccionario(self):
        """Así queda guardado en datos/descansos.json."""
        return {
            "nombre": self.nombre,
            "origen": self.origen,
            "inicio": self.inicio.strftime(FORMATO_FECHA),
            "fin": self.fin.strftime(FORMATO_FECHA),
            "duracion_planeada_min": round(self.duracion_planeada_s / SEGUNDOS_POR_MINUTO, DECIMALES_MINUTOS),
            "duracion_real_min": round(
                (self.fin - self.inicio).total_seconds() / SEGUNDOS_POR_MINUTO, DECIMALES_MINUTOS
            ),
            "completado": self.completado,
        }


class GestorDescansos:
    def __init__(self, archivo, ahora=datetime.now):
        """archivo: ArchivoDescansos (datos/descansos.json)."""
        self.archivo = archivo
        self.ahora = ahora
        self.historial = archivo["historial"]
        self.alerta_pendiente = False
        self.actual = None  # el Descanso en curso, o None
        self.medicion = None

    def conectar_medicion(self, medicion):
        """Se llama al encender (con la sesión) y al apagar (con None)."""
        self.medicion = medicion
        if medicion is not None and self.en_descanso():
            medicion.pausar_alertas(True)

    def en_descanso(self):
        return self.actual is not None

    # --- Alerta de fatiga ---

    def recibir_alerta(self):
        """Devuelve True si hay que mostrar la alerta (no hay otra pendiente ni un descanso en curso)."""
        if self.alerta_pendiente or self.en_descanso():
            return False
        self.alerta_pendiente = True
        return True

    def aceptar_alerta(self, minutos):
        self.alerta_pendiente = False
        return self.iniciar(NOMBRE_DESCANSO_FATIGA, ORIGEN_FATIGA, minutos)

    # --- Descansos ---

    def iniciar_manual(self, minutos, nombre=None):
        """Descanso que el usuario toma por su cuenta. Con una alerta pendiente se usa Aceptar."""
        if self.alerta_pendiente or self.en_descanso():
            return None
        validar_minutos(minutos)
        return self.iniciar(nombre or NOMBRE_DESCANSO_LIBRE, ORIGEN_MANUAL, minutos)

    def iniciar(self, nombre, origen, minutos):
        self.actual = Descanso(nombre, origen, self.ahora(), minutos * SEGUNDOS_POR_MINUTO)
        if self.medicion is not None:
            self.medicion.pausar_alertas(True)
        return self.actual

    def segundos_restantes(self):
        if self.actual is None:
            return 0
        transcurrido = (self.ahora() - self.actual.inicio).total_seconds()
        return max(self.actual.duracion_planeada_s - transcurrido, 0)

    def termino_el_tiempo(self):
        return self.en_descanso() and self.segundos_restantes() <= 0

    def terminar(self, completado):
        """
        Termina el descanso actual, lo guarda en el historial y rearma la alerta.
        completado=False si se usó "Terminar antes" o se cerró la app.
        """
        descanso = self.actual
        if descanso is None:
            return None
        descanso.fin = self.ahora()
        descanso.completado = completado
        self.actual = None

        self.historial.append(descanso.como_diccionario())
        self.archivo.guardar()

        if self.medicion is not None:
            self.medicion.pausar_alertas(False)
            self.medicion.rearmar_alerta()
        return descanso

    # --- Historial ---

    def descansos_del_dia(self, dia=None):
        dia = (dia or self.ahora().date()).isoformat()
        return [d for d in self.historial if d["inicio"].startswith(dia)]

    def minutos_del_dia(self, dia=None):
        return sum(d["duracion_real_min"] for d in self.descansos_del_dia(dia))


def validar_plantilla(nombre, minutos):
    if not nombre.strip():
        raise ValueError("La plantilla necesita un nombre.")
    validar_minutos(minutos)


class PlantillasDescanso:
    """Plantillas de descanso guardadas en descansos.json (sección "plantillas")."""

    def __init__(self, archivo):
        self.archivo = archivo

    def lista(self):
        return self.archivo["plantillas"]

    def agregar(self, nombre, minutos):
        validar_plantilla(nombre, minutos)
        self.revisar_nombre_repetido(nombre)
        self.lista().append({"nombre": nombre.strip(), "duracion_min": minutos})
        self.archivo.guardar()

    def editar(self, indice, nombre, minutos):
        validar_plantilla(nombre, minutos)
        self.revisar_nombre_repetido(nombre, salvo=indice)
        self.lista()[indice] = {"nombre": nombre.strip(), "duracion_min": minutos}
        self.archivo.guardar()

    def borrar(self, indice):
        del self.lista()[indice]
        self.archivo.guardar()

    def revisar_nombre_repetido(self, nombre, salvo=None):
        for indice, plantilla in enumerate(self.lista()):
            if indice != salvo and plantilla["nombre"].lower() == nombre.strip().lower():
                raise ValueError(f'Ya existe una plantilla llamada "{plantilla["nombre"]}".')
