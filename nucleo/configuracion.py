"""
Configuración de la app (config.json).

- La primera vez, config.json se crea copiando config.ejemplo.json.
- Si config.ejemplo.json trae claves nuevas que un config.json antiguo no tiene,
  se agregan con su valor por defecto.
- Los parámetros de detección valen null mientras el usuario no los cambie.
  null significa "usar el valor del original" (Código_Bitalino_Python.py), así un
  cambio en el original llega a la app. Lo que el usuario cambie tiene prioridad.
- El original nunca se modifica.

Qué se puede editar aquí: PARAMETROS_DETECCION (qué constantes del original se
pueden cambiar desde la app) y LIMITES_PARAMETROS (qué valores se aceptan).
"""

import copy
import json
import math
from pathlib import Path

from nucleo import rutas

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


def validar_parametro(nombre, valor):
    minimo, maximo = LIMITES_PARAMETROS[nombre]
    if not minimo <= valor <= maximo:
        raise ValueError(f"{nombre} debe estar entre {minimo:g} y {maximo:g}.")


def completar(valores, por_defecto):
    """Agrega a 'valores' las claves de 'por_defecto' que falten (también en subsecciones)."""
    resultado = copy.deepcopy(por_defecto)
    for clave, valor in valores.items():
        if isinstance(valor, dict) and isinstance(resultado.get(clave), dict):
            resultado[clave] = completar(valor, resultado[clave])
        else:
            resultado[clave] = valor
    return resultado


class Configuracion:
    def __init__(self, carpeta_base, carpeta_recursos=None):
        carpeta_recursos = Path(carpeta_recursos or rutas.carpeta_recursos())
        self.ruta = Path(carpeta_base) / rutas.NOMBRE_CONFIG
        ruta_ejemplo = carpeta_recursos / rutas.NOMBRE_CONFIG_EJEMPLO
        self.por_defecto = json.loads(ruta_ejemplo.read_text(encoding="utf-8"))
        self.datos = self.leer()

    def leer(self):
        """Lee config.json; si no existe, lo crea desde el ejemplo."""
        if not self.ruta.exists():
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            self.escribir(self.por_defecto)
            return copy.deepcopy(self.por_defecto)

        try:
            guardados = json.loads(self.ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # Archivo dañado (ej. editado a mano con un error): se guarda aparte y se rehace.
            self.ruta.replace(self.ruta.with_name(rutas.NOMBRE_CONFIG + ".dañado"))
            self.escribir(self.por_defecto)
            return copy.deepcopy(self.por_defecto)

        return completar(guardados, self.por_defecto)

    def escribir(self, datos):
        texto = json.dumps(datos, indent=2, ensure_ascii=False)
        self.ruta.write_text(texto + "\n", encoding="utf-8")

    def guardar(self):
        self.escribir(self.datos)

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
