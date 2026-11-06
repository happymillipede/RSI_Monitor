"""
Conexión automática con el BITalino por Bluetooth (como puerto serie).

1. Se arma la lista de puertos a probar (lista_candidatos): el puerto manual de los
   ajustes si hay uno; si no, el último que funcionó, el PUERTO del original y los
   que se encuentran solos:
   - macOS: /dev/tty.* que tengan "bitalino" en el nombre;
   - Windows: los puertos COM de Bluetooth (BTHENUM en su identificador);
   - Linux (solo para desarrollar): /dev/rfcomm*.
2. Cada puerto se abre y se valida pidiéndole la versión al BITalino (version()),
   con un límite de tiempo, para que la app nunca se quede colgada.
3. Si ninguno responde, se espera y se vuelve a buscar. La espera crece
   (1, 2, 4, 8... s) hasta un máximo, y se interrumpe apenas el usuario aprieta Apagar.

El paquete bitalino, en modo bloqueante, espera para siempre si el equipo no responde;
y con su opción "timeout" ocupa un núcleo entero de la CPU mientras espera. Por eso
aquí cada operación corre en un hilo auxiliar con un límite de tiempo
(ejecutar_con_limite) y, si se pasa o si el usuario aprieta Apagar, se
cierra el puerto.

Qué se puede editar aquí: PUERTO_ENTRANTE_WINDOWS, REVISION_S y LIMITE_DETENER_S.
Los tiempos de espera están en config.json (sección "conexion").
"""

import glob
import sys
import threading
import time

from app.nucleo.adquisicion import BUSCANDO, CONECTANDO

# En Windows cada equipo Bluetooth crea dos puertos COM. El "entrante" (que no sirve
# para conectarse al BITalino) suele tener este texto en su identificador: se prueba al final.
PUERTO_ENTRANTE_WINDOWS = "LOCALMFG&0000"

# Mientras se espera al BITalino, cada cuánto se revisa si el usuario pidió detener.
REVISION_S = 0.1
# Límite para stop() al apagar: es solo enviar un byte, y la app no debe demorar en cerrarse.
LIMITE_DETENER_S = 2


def ejecutar_con_limite(funcion, limite_s, detener=None):
    """
    Ejecuta funcion() en un hilo auxiliar y espera como máximo limite_s segundos.
    Devuelve lo que devuelve funcion() o relanza su error. Lanza TimeoutError si se
    pasa del límite, o InterruptedError si antes se activa 'detener' (threading.Event).
    """
    resultado = {}

    def trabajar():
        try:
            resultado["valor"] = funcion()
        except BaseException as error:
            resultado["error"] = error

    hilo = threading.Thread(target=trabajar, daemon=True)
    hilo.start()
    fin = time.monotonic() + limite_s
    while hilo.is_alive():
        if detener is not None and detener.is_set():
            raise InterruptedError("se pidió detener")
        restante = fin - time.monotonic()
        if restante <= 0:
            raise TimeoutError(f"el BITalino no respondió en {limite_s:g} s")
        hilo.join(min(restante, REVISION_S))
    if "error" in resultado:
        raise resultado["error"]
    return resultado["valor"]


def listar_puertos_serie():
    """Todos los puertos serie que ve pyserial."""
    from serial.tools import list_ports

    return list_ports.comports()


def puertos_detectados(sistema=sys.platform, listar=listar_puertos_serie, buscar_archivos=glob.glob):
    """Puertos donde podría estar el BITalino, según el sistema operativo."""
    if sistema == "win32":
        bluetooth = [p for p in listar() if "BTHENUM" in (p.hwid or "").upper()]
        bluetooth.sort(key=lambda p: PUERTO_ENTRANTE_WINDOWS in p.hwid.upper())
        return [p.device for p in bluetooth]
    if sistema == "darwin":
        return sorted(ruta for ruta in buscar_archivos("/dev/tty.*") if "bitalino" in ruta.lower())
    return sorted(buscar_archivos("/dev/rfcomm*"))


def todos_los_puertos():
    """Para elegir un puerto a mano en los ajustes: los detectados y todos los demás."""
    puertos = puertos_detectados()
    for puerto in listar_puertos_serie():
        if puerto.device not in puertos:
            puertos.append(puerto.device)
    return puertos


def lista_candidatos(puerto_manual, ultimo_puerto, puerto_original, detectados):
    """Orden en que se prueban los puertos (sin repetir). El manual reemplaza a todos."""
    if puerto_manual:
        return [puerto_manual]
    candidatos = []
    for puerto in [ultimo_puerto, puerto_original, *detectados]:
        if puerto and puerto not in candidatos:
            candidatos.append(puerto)
    return candidatos


def tiempo_de_espera(intento, espera_inicial_s, espera_maxima_s):
    """Espera antes del intento siguiente: 1, 2, 4, 8... s, sin pasar del máximo."""
    return min(espera_inicial_s * 2**intento, espera_maxima_s)


def cerrar_puerto(dispositivo):
    """Cierra el puerto serie. Si un read() estaba esperando, se corta con un error."""
    puerto = getattr(dispositivo, "socket", None)
    if puerto is not None:
        try:
            puerto.close()
        except Exception:
            pass


class BitalinoConLimite:
    """
    El BITalino real con un límite de tiempo en cada operación. Se usa igual que
    bitalino.BITalino: start(), read(), stop(), close(), version().
    """

    def __init__(self, puerto, limite_s, detener=None, clase_bitalino=None):
        """detener: threading.Event; si se activa, la operación en curso se corta enseguida."""
        if clase_bitalino is None:
            from bitalino import BITalino as clase_bitalino
        self.puerto = puerto
        self.limite_s = limite_s
        self.detener = detener
        self.fs = None

        # El objeto se crea antes de conectarse, para poder cerrar su puerto si el
        # BITalino no responde. Al conectarse, el paquete bitalino ya pide la versión.
        self.dispositivo = clase_bitalino.__new__(clase_bitalino)
        self.con_limite(lambda: clase_bitalino.__init__(self.dispositivo, puerto))
        self.texto_version = self.con_limite(self.dispositivo.version)

    def con_limite(self, funcion, limite_s=None, interrumpible=True):
        try:
            return ejecutar_con_limite(funcion, limite_s or self.limite_s, self.detener if interrumpible else None)
        except Exception:
            cerrar_puerto(self.dispositivo)
            raise

    def version(self):
        return self.texto_version

    def start(self, fs, canales):
        self.fs = fs
        self.con_limite(lambda: self.dispositivo.start(fs, canales))

    def read(self, n):
        # Leer n muestras demora n / fs segundos; el límite es eso más el de la conexión.
        return self.con_limite(lambda: self.dispositivo.read(n), n / self.fs + self.limite_s)

    def stop(self):
        # Se llama justo después de apretar Apagar: no se interrumpe, pero tiene un límite corto.
        self.con_limite(self.dispositivo.stop, LIMITE_DETENER_S, interrumpible=False)

    def close(self):
        cerrar_puerto(self.dispositivo)


class ConectorBitalino:
    def __init__(self, conexion, puerto_original, abrir=BitalinoConLimite, buscar_puertos=puertos_detectados):
        """
        conexion: la sección "conexion" de config.json (puerto_manual, ultimo_puerto,
        timeout_s, espera_inicial_s, espera_maxima_s). Se lee en cada intento.
        puerto_original: PUERTO de Código_Bitalino_Python.py.
        """
        self.conexion = conexion
        self.puerto_original = puerto_original
        self.abrir = abrir
        self.buscar_puertos = buscar_puertos

    def candidatos(self):
        return lista_candidatos(
            self.conexion["puerto_manual"],
            self.conexion["ultimo_puerto"],
            self.puerto_original,
            self.buscar_puertos(),
        )

    def __call__(self, detener, avisar):
        """
        Busca el BITalino hasta encontrarlo o hasta que se pida detener.
        detener: threading.Event. avisar(estado, detalle): para mostrar qué está pasando.
        Devuelve el dispositivo conectado, o None si se pidió detener.
        """
        intento = 0
        while not detener.is_set():
            avisar(BUSCANDO, "Buscando el BITalino…")
            errores = []
            for puerto in self.candidatos():
                if detener.is_set():
                    return None
                avisar(CONECTANDO, f"Probando {puerto}…")
                try:
                    return self.abrir(puerto, self.conexion["timeout_s"], detener)
                except Exception as error:
                    errores.append(f"{puerto}: {error or type(error).__name__}")

            espera = tiempo_de_espera(intento, self.conexion["espera_inicial_s"], self.conexion["espera_maxima_s"])
            motivo = "; ".join(errores) if errores else "no hay puertos Bluetooth del BITalino"
            avisar(BUSCANDO, f"No se encontró el BITalino ({motivo}). Nuevo intento en {espera:g} s.")
            if detener.wait(espera):
                return None
            intento += 1
        return None
