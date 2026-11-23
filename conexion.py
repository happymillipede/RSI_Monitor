"""
Conexión con el BITalino por Bluetooth (como puerto serie).

El paquete bitalino abre un puerto serie si el nombre empieza con "COM" (Windows) o
"/dev/" (macOS); con una dirección MAC usa PyBluez. La app siempre usa el puerto serie.

- puertos_detectados(): puertos donde podría estar el BITalino:
    macOS: /dev/tty.* con "bitalino" en el nombre; Windows: los COM de Bluetooth
    (BTHENUM), con el "entrante" al final; Linux (para desarrollar): /dev/rfcomm*.
- BitalinoConLimite: el BITalino con un tiempo máximo en cada operación. Si el equipo
  no responde, el paquete bitalino se queda esperando para siempre (y su opción
  "timeout" ocupa un núcleo entero de la CPU). Aquí cada operación corre en un hilo
  auxiliar con un límite y, si se pasa, se cierra el puerto.
- conectar_automatico(): prueba el último puerto que funcionó, el PUERTO del notebook
  y los detectados, en ese orden.

Qué se puede editar aquí: PUERTO_ENTRANTE_WINDOWS, LIMITE_DETENER_S y los textos de explicar_error().
"""

import glob
import sys
import threading
import time

# En Windows cada equipo Bluetooth crea dos puertos COM. El "entrante" (que no sirve
# para conectarse al BITalino) suele tener este texto en su identificador: se prueba al final.
PUERTO_ENTRANTE_WINDOWS = "LOCALMFG&0000"
REVISION_S = 0.1  # cada cuánto se revisa si se pidió cancelar mientras se espera
LIMITE_DETENER_S = 2  # stop() es solo enviar un byte: no debe demorar


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
            raise InterruptedError("se pidió cancelar")
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


def todos_los_puertos(detectados=None, listar=listar_puertos_serie):
    """Los detectados primero y después todos los demás puertos serie."""
    puertos = list(puertos_detectados() if detectados is None else detectados)
    for puerto in listar():
        if puerto.device not in puertos:
            puertos.append(puerto.device)
    return puertos


def lista_candidatos(ultimo_puerto, puerto_original, detectados):
    """Orden en que se prueban los puertos al conectar automáticamente (sin repetir)."""
    candidatos = []
    for puerto in [ultimo_puerto, puerto_original, *detectados]:
        if puerto and puerto not in candidatos:
            candidatos.append(puerto)
    return candidatos


def cerrar_puerto(dispositivo):
    """Cierra el puerto serie. Si un read() estaba esperando, se corta con un error."""
    puerto = getattr(dispositivo, "socket", None)
    if puerto is not None:
        try:
            puerto.close()
        except Exception:
            pass


def explicar_error(puerto, error):
    """El error de un puerto en palabras simples."""
    texto = str(error) or type(error).__name__
    if isinstance(error, TimeoutError):
        return f"{puerto}: el BITalino no respondió. Revisa que esté encendido y cerca del computador."
    if "could not open port" in texto or isinstance(error, FileNotFoundError):
        return f"{puerto}: no se pudo abrir el puerto. Revisa que el BITalino esté emparejado por Bluetooth."
    if "Access is denied" in texto or isinstance(error, PermissionError):
        return f"{puerto}: el puerto está ocupado o sin permiso. Cierra otros programas que lo usen."
    return f"{puerto}: {texto}."


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
        self.con_limite(self.dispositivo.stop, LIMITE_DETENER_S, interrumpible=False)

    def close(self):
        cerrar_puerto(self.dispositivo)


def conectar_automatico(candidatos, limite_s, detener=None, abrir=BitalinoConLimite, avisar=None):
    """Prueba cada puerto. Devuelve el BITalino conectado o lanza LookupError con los motivos."""
    errores = []
    for puerto in candidatos:
        if detener is not None and detener.is_set():
            raise InterruptedError("se pidió cancelar")
        if avisar:
            avisar(f"Probando {puerto}…")
        try:
            return abrir(puerto, limite_s, detener)
        except InterruptedError:
            raise
        except Exception as error:
            errores.append(explicar_error(puerto, error))
    if not errores:
        raise LookupError("No se encontró ningún puerto Bluetooth del BITalino. ¿Está emparejado?")
    raise LookupError(" ".join(errores))
