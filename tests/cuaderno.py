"""
Ejecuta el código del notebook del grupo (originales/bitalino_codigo (Ver 4.2).ipynb)
tal cual, para comparar sus resultados con los de la app.

- Se ignoran las líneas que empiezan con % (%pip install).
- IPython y matplotlib se reemplazan por imitaciones que no dibujan nada; las
  alertas que el notebook muestra con display(HTML(...)) quedan anotadas.
- No se ejecuta la celda 5 (conexión con el BITalino real) ni la 8 (gráficos).
- El simulador del notebook se usa sin esperar tiempo real.
"""

import ast
import contextlib
import io
import json
import os
import sys
import types
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA_NOTEBOOK = RAIZ / "originales" / "bitalino_codigo (Ver 4.2).ipynb"

# Celdas del notebook 4.2
CELDA_IMPORTS = 1
CELDA_CONFIGURACION = 2
CELDA_SIMULADOR = 3
CELDA_HTML = 4
CELDA_PROCESADOR = 6
CELDA_ESTADO = 7
CELDA_REPOSO = 9
CELDA_MVC = 10
CELDA_ADQUISICION = 11

VELOCIDAD_SIN_ESPERA = 1e9


def leer_celdas(ruta=RUTA_NOTEBOOK):
    cuaderno = json.loads(Path(ruta).read_text(encoding="utf-8"))
    celdas = []
    for celda in cuaderno["cells"]:
        texto = "".join(celda["source"]) if celda["cell_type"] == "code" else ""
        lineas = ["" if linea.lstrip().startswith("%") else linea for linea in texto.splitlines()]
        celdas.append("\n".join(lineas))
    return celdas


def constantes_de_celda(numero, ruta=RUTA_NOTEBOOK):
    """Asignaciones simples (NOMBRE = valor literal) de una celda, sin ejecutarla."""
    constantes = {}
    for nodo in ast.parse(leer_celdas(ruta)[numero]).body:
        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1 and isinstance(nodo.targets[0], ast.Name):
            try:
                constantes[nodo.targets[0].id] = ast.literal_eval(nodo.value)
            except ValueError:
                pass
    return constantes


def modulos_imitados(alertas):
    """IPython.display y matplotlib.pyplot falsos."""
    ipython = types.ModuleType("IPython")
    display = types.ModuleType("IPython.display")
    display.HTML = lambda texto: texto
    display.Javascript = lambda texto: texto
    display.display = lambda objeto, **opciones: alertas.append(objeto) if isinstance(objeto, str) else None
    ipython.display = display
    matplotlib = types.ModuleType("matplotlib")
    pyplot = types.ModuleType("matplotlib.pyplot")
    matplotlib.pyplot = pyplot
    return {"IPython": ipython, "IPython.display": display, "matplotlib": matplotlib, "matplotlib.pyplot": pyplot}


def ejecutar_notebook(carpeta, modo, duracion_s, con_mvc=False, ejecutar_adquisicion=True):
    """
    Corre el notebook en 'carpeta' con el simulador en el modo dado y DURACION = duracion_s.
    con_mvc=True: ejecuta también calibrar_mvc() (sin las esperas de time.sleep).
    Devuelve (espacio de nombres, texto impreso, alertas mostradas).
    """
    celdas = leer_celdas()
    alertas = []
    salida = io.StringIO()
    anteriores = {nombre: sys.modules.get(nombre) for nombre in modulos_imitados([])}
    sys.modules.update(modulos_imitados(alertas))
    directorio = os.getcwd()
    espacio = {"__name__": "notebook"}
    try:
        os.chdir(carpeta)
        with contextlib.redirect_stdout(salida):
            exec(celdas[CELDA_IMPORTS], espacio)
            exec(celdas[CELDA_CONFIGURACION], espacio)
            espacio["DURACION"] = duracion_s
            exec(celdas[CELDA_SIMULADOR], espacio)
            espacio["device"] = espacio["BITalinoSimulado"](velocidad=VELOCIDAD_SIN_ESPERA, modo=modo)
            exec(celdas[CELDA_HTML], espacio)
            exec(celdas[CELDA_PROCESADOR], espacio)
            exec(celdas[CELDA_ESTADO], espacio)
            # Celda 8 (gráficos): solo se reemplazan sus funciones.
            espacio["actualizar_grafico"] = lambda *argumentos: None
            espacio["actualizar_graficos_bloque"] = lambda: None
            espacio["actualizar_panel_adquisicion"] = lambda: None
            exec(celdas[CELDA_REPOSO], espacio)
            exec(celdas[CELDA_MVC], espacio)
            if con_mvc:
                # Las cuentas regresivas y descansos de la MVC no cambian el resultado: se saltan.
                espacio["time"] = types.SimpleNamespace(sleep=lambda segundos: None, monotonic=espacio["time"].monotonic)
                exec("calibrar_mvc()", espacio)
            if ejecutar_adquisicion:
                exec(celdas[CELDA_ADQUISICION], espacio)
    finally:
        os.chdir(directorio)
        for nombre, modulo in anteriores.items():
            if modulo is None:
                sys.modules.pop(nombre, None)
            else:
                sys.modules[nombre] = modulo
    return espacio, salida.getvalue(), alertas
