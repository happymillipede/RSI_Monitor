"""
Almacenamiento en disco: dónde están los archivos, config.json y descansos.json.

Carpetas (iguales en el computador y en Docker):
    RSI_Monitor/
    ├─ Código_Bitalino_Python.py   el original (se busca aquí)
    ├─ backend/config.ejemplo.json valores por defecto
    ├─ backend/estaticos/          frontend compilado
    └─ datos/                      config.json, descansos.json y un CSV por sesión

config.json:
- La primera vez se crea copiando config.ejemplo.json.
- Si config.ejemplo.json trae claves nuevas que un config.json antiguo no tiene,
  se agregan con su valor por defecto.
- Los parámetros de detección valen null mientras el usuario no los cambie.
  null significa "usar el valor del original" (Código_Bitalino_Python.py), así un
  cambio en el original llega a la app. Lo que el usuario cambie tiene prioridad.
- El original nunca se modifica.

descansos.json tiene tres secciones: "plantillas", "historial" y "uso_diario"
(el reloj de uso de cada día).

Los JSON se guardan primero en un archivo temporal y después se reemplaza el
original, para que un corte de luz no los deje a medio escribir. Si uno está
dañado, se guarda aparte con ".dañado" y se parte de cero.

Qué se puede editar aquí: los nombres de archivos y carpetas, PARAMETROS_DETECCION
(qué constantes del original se pueden cambiar desde la app) y LIMITES_PARAMETROS
(qué valores se aceptan).
"""

import copy
import json
import math
import unicodedata
from pathlib import Path

NOMBRE_ORIGINAL = "Código_Bitalino_Python.py"
NOMBRE_CONFIG = "config.json"
NOMBRE_CONFIG_EJEMPLO = "config.ejemplo.json"
NOMBRE_DESCANSOS = "descansos.json"
NOMBRE_CARPETA_DATOS = "datos"
NOMBRE_CARPETA_ESTATICOS = "estaticos"

RAIZ_BACKEND = Path(__file__).resolve().parent.parent  # carpeta backend/
RAIZ_PROYECTO = RAIZ_BACKEND.parent  # carpeta RSI_Monitor/
CARPETA_DATOS = RAIZ_PROYECTO / NOMBRE_CARPETA_DATOS
CARPETA_ESTATICOS = RAIZ_BACKEND / NOMBRE_CARPETA_ESTATICOS
RUTA_CONFIG_EJEMPLO = RAIZ_BACKEND / NOMBRE_CONFIG_EJEMPLO

# Constantes del original que el usuario puede cambiar en los ajustes.
# Cada una tiene su versión SIM_ en la celda de simulación del original.
PARAMETROS_DETECCION = (
    "TREND_INTERVAL_S",
    "BASELINE_DURATION_S",
    "ALERT_PERSISTENCE_S",
    "RMS_INCREASE_THRESHOLD",
    "MDF_DECREASE_THRESHOLD",
)

# Valores que se aceptan en los ajustes: (mínimo, máximo). Los umbrales son fracciones (0.20 = 20 %).
LIMITES_PARAMETROS = {
    "TREND_INTERVAL_S": (0.1, 600),
    "BASELINE_DURATION_S": (0.1, 3600),
    "ALERT_PERSISTENCE_S": (0.1, 3600),
    "RMS_INCREASE_THRESHOLD": (0.0, 5.0),
    "MDF_DECREASE_THRESHOLD": (0.0, 0.99),
}

# --- Rutas ---


def carpeta_datos(carpeta=CARPETA_DATOS):
    """Carpeta datos/ (se crea si no existe)."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def buscar_archivo(carpeta, nombre):
    """
    Busca 'nombre' dentro de 'carpeta'. Compara los nombres normalizados (NFC)
    porque macOS puede guardar la "ó" de "Código" como dos caracteres (NFD).
    """
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return None

    buscado = unicodedata.normalize("NFC", nombre)
    for ruta in carpeta.iterdir():
        if unicodedata.normalize("NFC", ruta.name) == buscado:
            return ruta
    return None


def buscar_original():
    """Ruta del código original, en la raíz del proyecto."""
    ruta = buscar_archivo(RAIZ_PROYECTO, NOMBRE_ORIGINAL)
    if ruta is None:
        raise FileNotFoundError(f"No se encontró {NOMBRE_ORIGINAL} en {RAIZ_PROYECTO}.")
    return ruta


# --- Archivos JSON ---


def leer_json(ruta, por_defecto):
    ruta = Path(ruta)
    if not ruta.exists():
        return copy.deepcopy(por_defecto)
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        ruta.replace(ruta.with_name(ruta.name + ".dañado"))
        return copy.deepcopy(por_defecto)


def guardar_json(ruta, datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporal.replace(ruta)


def completar(valores, por_defecto):
    """Agrega a 'valores' las claves de 'por_defecto' que falten (también en subsecciones)."""
    resultado = copy.deepcopy(por_defecto)
    for clave, valor in valores.items():
        if isinstance(valor, dict) and isinstance(resultado.get(clave), dict):
            resultado[clave] = completar(valor, resultado[clave])
        else:
            resultado[clave] = valor
    return resultado


# --- config.json ---


def validar_parametro(nombre, valor):
    minimo, maximo = LIMITES_PARAMETROS[nombre]
    if not minimo <= valor <= maximo:
        raise ValueError(f"{nombre} debe estar entre {minimo:g} y {maximo:g}.")


class Configuracion:
    def __init__(self, carpeta_datos, ruta_ejemplo=RUTA_CONFIG_EJEMPLO):
        self.ruta = Path(carpeta_datos) / NOMBRE_CONFIG
        self.por_defecto = json.loads(Path(ruta_ejemplo).read_text(encoding="utf-8"))
        self.datos = completar(leer_json(self.ruta, {}), self.por_defecto)
        if not self.ruta.exists():
            self.guardar()

    def guardar(self):
        guardar_json(self.ruta, self.datos)

    def __getitem__(self, seccion):
        return self.datos[seccion]

    def parametros_deteccion(self, constantes, usar_umbrales_sim=False):
        """
        Parámetros de la regla de fatiga, con los mismos nombres del original.
        - usar_umbrales_sim=True: los SIM_* del original (celda de simulación).
        - Si no: el valor de config.json, o el del original si es null.
        """
        parametros = {}
        for nombre in PARAMETROS_DETECCION:
            if usar_umbrales_sim:
                parametros[nombre] = constantes["SIM_" + nombre]
                continue
            valor = self.datos["parametros_deteccion"].get(nombre)
            parametros[nombre] = constantes[nombre] if valor is None else valor
        return parametros

    def poner_parametro(self, nombre, valor, constantes):
        """
        Guarda un parámetro de detección elegido en los ajustes (sin escribir el archivo).
        Si es igual al del original (o None) queda null, para seguir los cambios del original.
        """
        if valor is not None:
            validar_parametro(nombre, valor)
            if math.isclose(valor, constantes[nombre]):
                valor = None
        self.datos["parametros_deteccion"][nombre] = valor

    def escenario_simulacion(self, constantes):
        """Escenario de config.json o, si es null, SIM_SCENARIO del original."""
        escenario = self.datos["simulacion"].get("escenario")
        return constantes["SIM_SCENARIO"] if escenario is None else escenario


# --- descansos.json ---


class ArchivoDescansos:
    """
    datos/descansos.json, compartido por las plantillas, el historial y el reloj de uso.
    Cada uno cambia su sección en 'datos' y llama a guardar().
    """

    def __init__(self, carpeta_datos, plantillas_iniciales):
        self.ruta = Path(carpeta_datos) / NOMBRE_DESCANSOS
        por_defecto = {"plantillas": plantillas_iniciales, "historial": [], "uso_diario": {}}
        self.datos = completar(leer_json(self.ruta, {}), por_defecto)

    def guardar(self):
        guardar_json(self.ruta, self.datos)

    def __getitem__(self, seccion):
        return self.datos[seccion]

    def __setitem__(self, seccion, valor):
        self.datos[seccion] = valor
