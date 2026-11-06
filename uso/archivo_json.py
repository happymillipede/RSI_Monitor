"""
Leer y guardar los archivos JSON de datos/ (uso diario e historial de descansos).

- Se guarda primero en un archivo temporal y después se reemplaza el original, para
  que un corte de luz no deje el archivo a medio escribir.
- Si un archivo está dañado, se guarda aparte con ".dañado" y se parte de cero.

Qué se puede editar aquí: nada en particular.
"""

import json
from pathlib import Path


def leer_json(ruta, por_defecto):
    ruta = Path(ruta)
    if not ruta.exists():
        return por_defecto
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        ruta.replace(ruta.with_name(ruta.name + ".dañado"))
        return por_defecto


def guardar_json(ruta, datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporal.replace(ruta)
