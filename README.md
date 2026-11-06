# RSI Monitor — Grupo 2

Detector de fatiga muscular para personas que usan el computador por mucho tiempo.
Usa un BITalino con 3 electrodos (sEMG por Bluetooth) y el código del grupo,
`Código_Bitalino_Python.py`, que **no se modifica**: la app lo lee con `ast` y toma de
ahí la clase `ProcesadorEMG` y las constantes (umbrales, tiempos, `SIM_*`).

> Estado: **Fase 3** (ventana con gráficos y panel, alerta de fatiga, ícono en la bandeja).
> Los descansos, los ajustes, la conexión al BITalino real y el empaquetado llegan en
> las fases siguientes; este README se completa en la Fase 7.

## Preparar el entorno (Python 3.10.11)

```bash
git clone <url-del-repositorio> RSI_Monitor
cd RSI_Monitor
```

macOS (con pyenv, como en el notebook):

```bash
pyenv install 3.10.11
pyenv local 3.10.11
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell, con el instalador de python.org 3.10.11):

```powershell
py -3.10 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Abrir la ventana

```bash
python app.py --sim
```

Elijan el escenario y la velocidad (×1 o ×10) y aprieten **Encender**. Primero se
calibra la línea base y después se ven las tendencias de RMS y MDF y el panel de
información (los mismos datos del original). Con `--umbrales-sim` se usan los umbrales
`SIM_*` del original, que en `fatigue_test` disparan la alerta: aparece la ventana
"Riesgo de fatiga muscular, descanse 10 minutos", que no se puede cerrar con la X ni con
Escape, solo con **Aceptar**. Cerrar la ventana principal deja la app en la bandeja; para
cerrarla del todo use **Salir** en el menú del ícono.

## Probar sin hardware y sin ventana

```bash
python app.py --sim --headless --velocidad 10 --escenario fatigue_test --umbrales-sim --duracion 60
```

Imprime los estados (Conectando → Calibrando línea base → Midiendo) y la alerta de
fatiga. Opciones: `--velocidad 0` (lo más rápido posible), `--escenario normal`,
`--detalle` (imprime cada intervalo), sin `--duracion` mide hasta Ctrl+C.
El CSV de cada sesión queda en `datos/`.

## Pruebas

```bash
python -m pytest -q
```

Las pruebas de equivalencia ejecutan la función `cerrar_intervalo()` y la celda de
simulación **reales** del original (con gráficos falsos) y comparan sus resultados
con los de la app.

## Configuración

La primera vez se crea `config.json` copiando `config.ejemplo.json`. En
`parametros_deteccion`, `null` significa "usar el valor del original": si cambian un
umbral en `Código_Bitalino_Python.py`, la app lo toma sin tocar nada más. Un número en
`config.json` tiene prioridad sobre el original.

## Resultado de la simulación con cada juego de umbrales

Señal simulada de 1000 s, semilla 42:

| Escenario      | Umbrales normales (+20 % / −15 % / 5 s) | Umbrales `SIM_*` (+5 % / −1 % / 1 s) |
|----------------|------------------------------------------|---------------------------------------|
| `fatigue_test` | **no alerta**                            | alerta a los ~17,5 s                   |
| `normal`       | no alerta                                | **alerta a los ~381 s** (falso positivo) |

- Con los umbrales normales, `fatigue_test` nunca alerta. La MDF baja ~40 %, pero el
  RMS sube solo ~3 % en promedio: la señal de 30–180 Hz tiene menos potencia que la de
  30–350 Hz y la amplitud ×1,5 casi solo lo compensa.
- Con los umbrales `SIM_*`, la condición es tan laxa (+5 % de RMS y −1 % de MDF durante
  un solo intervalo) que la señal `normal` también termina alertando por azar.

## Observaciones sobre el original (no se corrigieron)

- `TREND_INTERVAL_S = 1  # Un punto de resumen cada 10 segundos`: el comentario no coincide con el valor.
- El comentario de `ALERT_PERSISTENCE_S` dice "mantener la alerta", pero en realidad es el
  tiempo que tiene que persistir el patrón para disparar la alerta.
- `ax_mdf.set_xlim(0, DURACION)` usa otro límite que `ax_rms` (después ambos se reemplazan).
- La presentación dice pasabanda 20–450 Hz (lámina 3) y 30 intervalos para la línea base y
  la persistencia; el código usa 25–400 Hz, 5 s y 5 s. La app usa los valores del código.
- En la simulación, la rampa de `fatigue_test` empieza en `SIM_BASELINE_DURATION_S` (1 s)
  aunque se usen los umbrales normales, cuya línea base dura 5 s: la línea base se mide
  con la rampa ya empezada.

## Paquete `bitalino` 1.2.6 (revisado)

- Por puerto serie (`COMx` en Windows, `/dev/tty.*` en macOS) usa `pyserial` y no necesita
  PyBluez. `import bluetooth` solo se usa al conectar por dirección MAC en Windows/Linux;
  en macOS la MAC no está soportada.
- Sin `timeout`, la lectura bloquea indefinidamente. Con `timeout`, espera cada byte en un
  ciclo activo que ocupa un núcleo entero de la CPU. Por eso la app usará el modo
  bloqueante y le pondrá su propio límite de tiempo desde otro hilo (Fase 6).
