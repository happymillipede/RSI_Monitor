"""
Punto de entrada de RSI Monitor.

Uso:
    python app.py                         abre la ventana
    python app.py --sim                   abre la ventana en modo simulación
    python app.py --sim --umbrales-sim    ídem, con los umbrales SIM_* del original
    python app.py --sim --headless --velocidad 10 --escenario fatigue_test --umbrales-sim --duracion 60
                                          mide sin ventana e imprime los estados y las alertas

Opciones del modo sin ventana (--headless):
    --velocidad V     1 = tiempo real, 10 = diez veces más rápido, 0 = lo más rápido posible
    --escenario E     normal o fatigue_test (por defecto, el de config.json o SIM_SCENARIO)
    --umbrales-sim    usa los umbrales SIM_* del original
    --duracion S      se detiene después de S segundos de señal (si no, hasta Ctrl+C)
    --detalle         imprime también cada intervalo de tendencia

Qué se puede editar aquí: nada en particular; la lógica está en nucleo/, uso/ y ui/.
"""

import argparse
import signal
import sys

from nucleo import rutas
from nucleo.adquisicion import Oyente, SesionMedicion, prefijo_csv
from nucleo.cargador_original import cargar_original
from nucleo.configuracion import Configuracion
from nucleo.regla_fatiga import MENSAJE_ALERTA_SIMULADA
from nucleo.simulador import DispositivoSimulado


def leer_argumentos(argumentos=None):
    lector = argparse.ArgumentParser(description="RSI Monitor: detector de fatiga muscular con BITalino.")
    lector.add_argument("--sim", action="store_true", help="usar el BITalino simulado")
    lector.add_argument("--headless", action="store_true", help="medir sin ventana e imprimir las alertas")
    lector.add_argument("--velocidad", type=float, default=None, help="velocidad de la simulación (1, 10; 0 = sin esperar)")
    lector.add_argument("--escenario", choices=["normal", "fatigue_test"], default=None)
    lector.add_argument("--umbrales-sim", action="store_true", help="usar los umbrales SIM_* del original")
    lector.add_argument("--duracion", type=float, default=None, help="segundos de señal a medir (modo sin ventana)")
    lector.add_argument("--detalle", action="store_true", help="imprimir cada intervalo (modo sin ventana)")
    lector.add_argument("--minimizado", action="store_true", help="abrir solo en la bandeja (al iniciar con el sistema)")
    return lector.parse_args(argumentos)


class OyenteConsola(Oyente):
    """Imprime en la consola lo que pasa durante la medición (modo --headless)."""

    def __init__(self, duracion_s, detalle, mensaje_alerta):
        self.duracion_s = duracion_s
        self.detalle = detalle
        self.mensaje_alerta = mensaje_alerta
        self.sesion = None
        self.alertas = 0

    def al_cambiar_estado(self, estado, detalle=""):
        print(f"Estado: {estado}" + (f" ({detalle})" if detalle else ""))

    def al_procesar_bloque(self, info):
        segundos = info.n_medicion * self.sesion.constantes["PERIODO"]
        if self.duracion_s is not None and segundos >= self.duracion_s:
            self.sesion.detener()

    def al_cerrar_intervalo(self, resumen, linea_base):
        if self.detalle:
            print(f"  t={resumen.tiempo:8.3f} s | RMS={resumen.rms:8.3f} | MDF={resumen.mdf:8.3f} Hz")

    def al_detectar_fatiga(self, resumen):
        self.alertas += 1
        print(f"\n[t={resumen.tiempo:.1f} s] ALERTA DE FATIGA: {self.mensaje_alerta}\n")


def ejecutar_sin_ventana(argumentos, original, configuracion, carpeta_base):
    if not argumentos.sim:
        print("Por ahora el modo sin ventana solo funciona con --sim.")
        return 2

    constantes = original.constantes
    parametros = configuracion.parametros_deteccion(constantes, argumentos.umbrales_sim)
    escenario = argumentos.escenario or configuracion.escenario_simulacion(constantes)
    velocidad = argumentos.velocidad
    if velocidad is None:
        velocidad = configuracion["simulacion"]["velocidad"]

    def abrir_dispositivo():
        return DispositivoSimulado(
            escenario,
            original.fs,
            inicio_rampa_s=constantes["SIM_BASELINE_DURATION_S"],
            velocidad=velocidad or None,
        )

    oyente = OyenteConsola(argumentos.duracion, argumentos.detalle, MENSAJE_ALERTA_SIMULADA)
    sesion = SesionMedicion(
        original,
        parametros,
        abrir_dispositivo,
        rutas.carpeta_datos(carpeta_base),
        prefijo_csv(constantes, simulacion=True),
        oyente,
    )
    oyente.sesion = sesion

    # Ctrl+C detiene la medición de forma ordenada (cierra el último intervalo y el dispositivo).
    signal.signal(signal.SIGINT, lambda *_: sesion.detener())

    print(f"Original: {original.ruta}")
    texto_velocidad = f"x{velocidad:g}" if velocidad else "sin esperar"
    print(f"Escenario: {escenario} | velocidad: {texto_velocidad} | parámetros: {parametros}")
    print(f"CSV: {sesion.ruta_csv}")
    sesion.ejecutar()

    linea_base = sesion.regla.linea_base()
    if linea_base:
        print(f"Línea base: RMS={linea_base[0]:.3f} ADC | MDF={linea_base[1]:.3f} Hz")
    if oyente.alertas == 0:
        print(f"Simulación terminada ({escenario}). La regla no disparó ninguna alerta.")
    print(f"Segundos de señal: {sesion.n_medicion * constantes['PERIODO']:.1f}")
    return 0


def principal(argumentos=None):
    argumentos = leer_argumentos(argumentos)

    try:
        original = cargar_original()
        carpeta_base = rutas.carpeta_base()
        configuracion = Configuracion(carpeta_base)
    except Exception as error:
        mensaje = f"No se pudo abrir RSI Monitor:\n{error}"
        if argumentos.headless:
            print(mensaje)
        else:
            from ui.aplicacion import mostrar_error_fatal

            mostrar_error_fatal(mensaje)
        return 1

    if argumentos.headless:
        return ejecutar_sin_ventana(argumentos, original, configuracion, carpeta_base)

    # La interfaz se importa solo aquí, para que el modo --headless no cargue las ventanas.
    from ui.aplicacion import ejecutar_ventana

    return ejecutar_ventana(argumentos, original, configuracion, carpeta_base)


if __name__ == "__main__":
    sys.exit(principal())
