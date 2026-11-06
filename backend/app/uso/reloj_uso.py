"""
Reloj de uso: cuánto tiempo se ha medido hoy y en la sesión actual.

- Corre solo mientras la medición está encendida y se pausa durante los descansos.
- El total del día se guarda en datos/descansos.json, sección "uso_diario"
  ({"2026-11-06": segundos}), y vuelve a cero cuando cambia la fecha.
- Es solo informativo: no influye en la alerta de fatiga.

El servidor llama a tick() una vez por segundo. El reloj y la fecha se pueden
reemplazar en las pruebas para simular el paso del tiempo.

Qué se puede editar aquí: MAXIMO_SALTO_S. Cada cuánto se guarda se
cambia en config.json (reloj_uso.guardar_cada_s).
"""

import time
from datetime import date
SECCION = "uso_diario"  # sección de descansos.json

# Si entre dos tick() pasa más que esto, el computador estuvo suspendido: ese tiempo no se cuenta.
MAXIMO_SALTO_S = 60

SEGUNDOS_POR_MINUTO = 60
SEGUNDOS_POR_HORA = 3600


def formato_reloj(segundos):
    """Ej.: 75 -> "01:15"; 3725 -> "1:02:05"."""
    segundos = int(max(segundos, 0))
    horas, resto = divmod(segundos, SEGUNDOS_POR_HORA)
    minutos, segundos = divmod(resto, SEGUNDOS_POR_MINUTO)
    if horas:
        return f"{horas}:{minutos:02d}:{segundos:02d}"
    return f"{minutos:02d}:{segundos:02d}"


class RelojUso:
    def __init__(self, archivo, guardar_cada_s, reloj=time.monotonic, hoy=date.today):
        """archivo: ArchivoDescansos (datos/descansos.json)."""
        self.archivo = archivo
        self.guardar_cada_s = guardar_cada_s
        self.reloj = reloj
        self.hoy = hoy

        self.segundos_por_dia = archivo[SECCION]
        self.segundos_sesion = 0.0
        self.midiendo = False
        self.en_descanso = False
        self.cambios_sin_guardar = False
        self.ultimo_tick = reloj()
        self.ultimo_guardado = self.ultimo_tick

    def corriendo(self):
        return self.midiendo and not self.en_descanso

    # Antes de cada cambio se llama a tick(), para sumar el tiempo hasta ese momento.

    def empezar_medicion(self):
        self.tick()
        self.midiendo = True
        self.segundos_sesion = 0.0

    def terminar_medicion(self):
        self.tick()
        self.midiendo = False
        self.guardar()

    def empezar_descanso(self):
        self.tick()
        self.en_descanso = True
        self.guardar()

    def terminar_descanso(self):
        self.tick()
        self.en_descanso = False

    def tick(self):
        ahora = self.reloj()
        transcurrido = ahora - self.ultimo_tick
        self.ultimo_tick = ahora

        if self.corriendo() and 0 < transcurrido <= MAXIMO_SALTO_S:
            fecha = self.hoy().isoformat()
            self.segundos_por_dia[fecha] = self.segundos_por_dia.get(fecha, 0.0) + transcurrido
            self.segundos_sesion += transcurrido
            self.cambios_sin_guardar = True

        if ahora - self.ultimo_guardado >= self.guardar_cada_s:
            self.guardar()

    def segundos_hoy(self):
        return self.segundos_por_dia.get(self.hoy().isoformat(), 0.0)

    def guardar(self):
        self.ultimo_guardado = self.reloj()
        if not self.cambios_sin_guardar:
            return
        for fecha, segundos in self.segundos_por_dia.items():
            self.segundos_por_dia[fecha] = round(segundos, 1)
        self.archivo.guardar()
        self.cambios_sin_guardar = False
