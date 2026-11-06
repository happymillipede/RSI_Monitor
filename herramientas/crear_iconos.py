"""
Crea los íconos de la app empaquetada (recursos/icono.png, .ico y .icns) con el mismo
dibujo del ícono de la bandeja (ui/bandeja.py).

Los íconos ya están en el repositorio: solo hay que volver a correr esto si cambia
el dibujo o el color:
    python herramientas/crear_iconos.py

Qué se puede editar aquí: TIPO_ICONO y TAMANOS.
"""

import sys
from pathlib import Path

# Para poder importar ui/ al correr este archivo desde cualquier carpeta.
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PySide6.QtGui import QGuiApplication

from ui.bandeja import ICONO_MIDIENDO, dibujar_icono

TIPO_ICONO = ICONO_MIDIENDO
CARPETA_RECURSOS = RAIZ / "recursos"
# Tamaño en píxeles de cada formato (.ico admite hasta 256; .icns de macOS, 512).
TAMANOS = {"png": 256, "ico": 256, "icns": 512}


def principal():
    app = QGuiApplication(sys.argv)  # Qt necesita una aplicación para dibujar
    CARPETA_RECURSOS.mkdir(exist_ok=True)
    for extension, lado in TAMANOS.items():
        ruta = CARPETA_RECURSOS / f"icono.{extension}"
        if not dibujar_icono(TIPO_ICONO, lado).save(str(ruta)):
            raise SystemExit(f"No se pudo guardar {ruta}")
        print(f"Creado {ruta}")


if __name__ == "__main__":
    principal()
