"""
Cargador del código original (Código_Bitalino_Python.py) sin ejecutarlo completo.

El original es un notebook exportado: si se importara, instalaría paquetes (%pip),
se conectaría al BITalino y mediría 120 s. Por eso aquí se lee como texto y con
el módulo ast se extrae solo:
- la clase ProcesadorEMG, junto con los imports que usa (numpy, scipy.signal), y
- las constantes simples (números y textos): CANAL, PERIODO, N, umbrales, SIM_*, etc.

Así, si el grupo cambia un filtro o un umbral en el original, la app toma el
cambio al volver a abrirse, sin tocar nada más.

Qué se puede editar aquí:
- CONSTANTES_REQUERIDAS: constantes que la app necesita encontrar en el original.
"""

import ast
from dataclasses import dataclass
from pathlib import Path

from nucleo import rutas

NOMBRE_CLASE = "ProcesadorEMG"

CONSTANTES_REQUERIDAS = (
    "PUERTO",
    "CANAL",
    "PERIODO",
    "N",
    "TREND_INTERVAL_S",
    "TREND_WINDOW_S",
    "BASELINE_DURATION_S",
    "ALERT_PERSISTENCE_S",
    "RMS_INCREASE_THRESHOLD",
    "MDF_DECREASE_THRESHOLD",
    "SIM_SCENARIO",
    "SIM_TREND_INTERVAL_S",
    "SIM_BASELINE_DURATION_S",
    "SIM_ALERT_PERSISTENCE_S",
    "SIM_RMS_INCREASE_THRESHOLD",
    "SIM_MDF_DECREASE_THRESHOLD",
)


class ErrorOriginal(Exception):
    """El código original no tiene lo que la app necesita."""


@dataclass
class CodigoOriginal:
    ruta: Path
    ProcesadorEMG: type
    constantes: dict

    @property
    def fs(self):
        # Igual que el original (línea 169): FS = 1 / PERIODO
        return 1 / self.constantes["PERIODO"]


def leer_sin_magicos(ruta):
    """Lee el archivo y vacía las líneas de Jupyter que empiezan con % (ej. %pip install)."""
    lineas = Path(ruta).read_text(encoding="utf-8").splitlines()
    # Se dejan vacías (en vez de borrarlas) para que los errores muestren la línea correcta.
    return "\n".join("" if linea.lstrip().startswith("%") else linea for linea in lineas)


def extraer_constantes(arbol):
    """Toma las asignaciones de nivel superior del tipo NOMBRE = valor simple."""
    constantes = {}
    for nodo in arbol.body:
        if not isinstance(nodo, ast.Assign) or len(nodo.targets) != 1:
            continue
        if not isinstance(nodo.targets[0], ast.Name):
            continue
        try:
            # Si el nombre se asigna dos veces, gana la última, igual que al ejecutar.
            constantes[nodo.targets[0].id] = ast.literal_eval(nodo.value)
        except (ValueError, TypeError, SyntaxError):
            pass  # No es un valor simple (ej. FS = 1 / PERIODO): se ignora.
    return constantes


def nombres_importados(nodo_import):
    """Nombres que deja disponibles un import (ej. 'import numpy as np' -> {'np'})."""
    return {(alias.asname or alias.name).split(".")[0] for alias in nodo_import.names}


def extraer_procesador(arbol, ruta, constantes):
    """Ejecuta solo la clase ProcesadorEMG y los imports que usa, y devuelve la clase."""
    clase = None
    for nodo in arbol.body:
        if isinstance(nodo, ast.ClassDef) and nodo.name == NOMBRE_CLASE:
            clase = nodo
    if clase is None:
        raise ErrorOriginal(f"No se encontró la clase {NOMBRE_CLASE} en {Path(ruta).name}.")

    nombres_usados = {nodo.id for nodo in ast.walk(clase) if isinstance(nodo, ast.Name)}
    imports_necesarios = [
        nodo
        for nodo in arbol.body
        if isinstance(nodo, (ast.Import, ast.ImportFrom))
        and nombres_importados(nodo) & nombres_usados
    ]

    modulo = ast.Module(body=imports_necesarios + [clase], type_ignores=[])
    # Las constantes quedan disponibles por si la clase llega a usar alguna.
    espacio = dict(constantes)
    espacio["__name__"] = "codigo_original"
    exec(compile(modulo, str(ruta), "exec"), espacio)
    return espacio[NOMBRE_CLASE]


def cargar_original(ruta=None):
    """Lee el original y devuelve la clase ProcesadorEMG y sus constantes."""
    ruta = Path(ruta) if ruta else rutas.buscar_original()
    texto = leer_sin_magicos(ruta)
    arbol = ast.parse(texto, filename=str(ruta))

    constantes = extraer_constantes(arbol)
    faltan = [nombre for nombre in CONSTANTES_REQUERIDAS if nombre not in constantes]
    if faltan:
        raise ErrorOriginal(
            f"En {ruta.name} faltan estas constantes: {', '.join(faltan)}."
        )

    procesador = extraer_procesador(arbol, ruta, constantes)
    return CodigoOriginal(ruta=ruta, ProcesadorEMG=procesador, constantes=constantes)
