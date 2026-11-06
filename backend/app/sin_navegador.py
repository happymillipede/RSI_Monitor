"""
Modo sin navegador (--headless): mide e imprime los estados y las alertas en la consola.
Sirve para probar rápido el núcleo, sin servidor ni frontend. Se usa desde app/main.py:

    python -m app.main --sim --headless --velocidad 10 --escenario fatigue_test --umbrales-sim --duracion 60
    python -m app.main --headless         ídem con el BITalino real (lo busca y se conecta solo)

Opciones:
    --velocidad V     1 = tiempo real, 10 = diez veces más rápido, 0 = lo más rápido posible
    --escenario E     normal o fatigue_test (por defecto, el de config.json o SIM_SCENARIO)
    --umbrales-sim    usa los umbrales SIM_* del original
    --duracion S      se detiene después de S segundos de señal (si no, hasta Ctrl+C)
    --detalle         imprime también cada intervalo de tendencia

Qué se puede editar aquí: los textos que se imprimen.
"""

import signal

from app.nucleo.adquisicion import Oyente, SesionMedicion, prefijo_csv
from app.nucleo.cargador_original import cargar_original
from app.nucleo.conexion import ConectorBitalino
from app.nucleo.regla_fatiga import MENSAJE_ALERTA_ORIGINAL, MENSAJE_ALERTA_SIMULADA
from app.nucleo.simulador import DispositivoSimulado


class OyenteConsola(Oyente):
    """Imprime en la consola lo que pasa durante la medición (modo --headless)."""

    def __init__(self, duracion_s, detalle, mensaje_alerta, configuracion):
        self.duracion_s = duracion_s
        self.detalle = detalle
        self.mensaje_alerta = mensaje_alerta
        self.configuracion = configuracion
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

    def al_conectar(self, puerto, version):
        if puerto is None:
            return
        print(f"Conectado al BITalino en {puerto} ({version})")
        self.configuracion["conexion"]["ultimo_puerto"] = puerto
        self.configuracion.guardar()


def ejecutar_sin_navegador(argumentos, original, configuracion, carpeta_datos):
    constantes = original.constantes
    simulacion = argumentos.sim
    parametros = configuracion.parametros_deteccion(constantes, simulacion and argumentos.umbrales_sim)

    if simulacion:
        escenario = argumentos.escenario or configuracion.escenario_simulacion(constantes)
        velocidad = argumentos.velocidad
        if velocidad is None:
            velocidad = configuracion["simulacion"]["velocidad"]

        def abrir_dispositivo(detener, avisar):
            return DispositivoSimulado(
                escenario,
                original.fs,
                inicio_rampa_s=constantes["SIM_BASELINE_DURATION_S"],
                velocidad=velocidad or None,
            )

        mensaje_alerta = MENSAJE_ALERTA_SIMULADA
    else:
        abrir_dispositivo = ConectorBitalino(configuracion["conexion"], constantes["PUERTO"])
        mensaje_alerta = MENSAJE_ALERTA_ORIGINAL

    oyente = OyenteConsola(argumentos.duracion, argumentos.detalle, mensaje_alerta, configuracion)
    sesion = SesionMedicion(
        original,
        parametros,
        abrir_dispositivo,
        carpeta_datos,
        prefijo_csv(constantes, simulacion),
        oyente,
        reconectar=not simulacion,
    )
    oyente.sesion = sesion

    # Ctrl+C detiene la medición de forma ordenada (cierra el último intervalo y el dispositivo).
    signal.signal(signal.SIGINT, lambda *_: sesion.detener())

    print(f"Original: {original.ruta}")
    if simulacion:
        texto_velocidad = f"x{velocidad:g}" if velocidad else "sin esperar"
        print(f"Escenario: {escenario} | velocidad: {texto_velocidad}")
    print(f"Parámetros: {parametros}")
    print(f"CSV: {sesion.ruta_csv}")
    try:
        sesion.ejecutar()
    except Exception as error:
        print(f"La medición se detuvo por un error: {error}")
        return 1

    linea_base = sesion.regla.linea_base()
    if linea_base:
        print(f"Línea base: RMS={linea_base[0]:.3f} ADC | MDF={linea_base[1]:.3f} Hz")
    if oyente.alertas == 0:
        print("Medición terminada. La regla no disparó ninguna alerta.")
    print(f"Segundos de señal: {sesion.n_medicion * constantes['PERIODO']:.1f}")
    return 0
