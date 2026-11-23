# RSI Monitor — Documentación técnica

Para usar la app basta con el [README](README.md). Este documento es para quien quiera
entender o cambiar el código.

## Cómo está armada

```
ventana (interfaz/: HTML + JS + CSS)  ── window.pywebview.api.<método>() ──▶  Api (app.py)
          ▲                                                                       │
          └──────── window.rsi.recibir(mensaje) (evaluate_js) ◀── hilo: conexión, calibración o grabación
```

- Es el mismo esquema del proyecto *BitalinoPywebview*: Python adquiere y procesa, y la
  ventana solo muestra los datos. JavaScript no recalcula nada.
- La conexión, la calibración y la grabación corren en un hilo aparte, para que la
  ventana nunca se congele. Solo hay una tarea a la vez.
- Python envía mensajes con un campo `tipo`: `estado` (la foto completa), `bloque`
  (cada bloque de 1 s), `tendencia` (cada 5 s), `alerta` y `mensaje`.
- La alerta abre una segunda ventana (`interfaz/alerta.html`) con `on_top=True`, que
  queda encima de las demás aplicaciones.

## Archivos

```
RSI_Monitor/
├─ originales/                 notebooks y presentación del grupo (no se tocan)
│  └─ bitalino_codigo (Ver 4.2).ipynb   la fuente de los cálculos
├─ app.py                      ventana pywebview, pop-up y Api (lo que llama JavaScript)
├─ configuracion.py            parámetros del notebook (celdas 2, 3 y 7) y de la app
├─ procesamiento.py            simulador (celda 3), ProcesadorEMG y calidad (celda 6)
├─ fatiga.py                   actividad, índice, tendencias y alerta (celdas 7 y 11)
├─ calibracion.py              comprobación de reposo (celda 9) y MVC (celda 10)
├─ grabacion.py                ciclo de grabación y los tres CSV (celda 11)
├─ conexion.py                 puertos y BITalino con tiempo límite
├─ interfaz/                   index.html, app.js, graficos.js, estilos.css, alerta.html
├─ tests/                      pruebas (cuaderno.py ejecuta el notebook para compararlo)
├─ iniciar.py                  instala la primera vez y abre la app
├─ generar_exe.py              .exe (Windows) o .app (macOS) con PyInstaller
└─ datos/                      CSV y ajustes.json (no van en git)
```

Cada archivo empieza con un comentario que dice qué hace y qué se puede editar.

## Cómo se usa el notebook 4.2

El código de las celdas está **copiado** en los módulos de arriba, con los mismos
cálculos y comentarios que dicen de qué celda viene. El notebook guarda todo en
variables globales; aquí ese estado vive en un objeto por grabación
(`AnalizadorFatiga`). Los parámetros de la celda 2 están en `configuracion.py` con los
mismos nombres y valores.

Para asegurar que la copia es fiel, `tests/cuaderno.py` **ejecuta el notebook tal
cual** (con imitaciones de IPython y matplotlib, sin la celda que conecta el BITalino
real ni la de los gráficos) y `tests/test_equivalencia.py` compara:

- los tres CSV, **byte a byte**, en los modos `normal`, `fatiga` y `contraccion`, con y
  sin MVC, y con los 10 min completos del notebook;
- el resultado de la calibración de reposo y lo que imprime;
- MVC_RMS y las alertas.

`tests/test_configuracion.py` compara los valores de `configuracion.py` con los del
notebook. **Si el grupo cambia el notebook**, hay que guardar la versión nueva en
`originales/`, actualizar la ruta en `tests/cuaderno.py` y correr las pruebas: dicen
exactamente qué dejó de coincidir.

## Qué cambia respecto del notebook

Ninguno de estos cambios toca los cálculos (las pruebas lo comprueban):

| Notebook 4.2 | App |
|---|---|
| graba `DURACION` = 10 min | graba hasta **Detener** (máximo 24 h, `DURACION_MAXIMA_S`). `DURACION` solo la usa el simulador para la rampa de fatiga |
| alerta una sola vez por grabación | al cerrar el pop-up, se rearma a los `REARME_ALERTA_MIN` (10) min de grabación |
| `FATIGUE_ALERT_THRESHOLD` fijo | es el «Porcentaje de alerta», editable en la ventana (se guarda en `datos/ajustes.json`) |
| se puede adquirir sin comprobar el reposo (el índice queda en NaN) | **Comenzar** pide calibrar primero, porque sin PASS nunca hay índice ni alerta |
| `device` es el simulador o el BITalino según la celda que se ejecute | se elige en **Conectar dispositivo** |
| `print()` y matplotlib | pestaña Detalles y gráficos en `<canvas>` |
| `time.sleep()` en el simulador y la MVC | esperas que se pueden cortar con Detener |
| `slope_history` crece sin límite | se olvidan los puntos fuera de la ventana de 20 s (no cambia el resultado) |

## Lo que calcula (resumen del notebook 4.2)

1. **Filtro**: notches de 50, 100, 150 y 250 Hz (dos en cascada cada uno, Q = 30) y
   pasabanda Butterworth de orden 4 entre 25 y 400 Hz. El estado del filtro sigue de un
   bloque al siguiente. Los primeros `SETTLING_S` = 2 s son «asentamiento».
2. **Por bloque de 1 s**: RMS, MDF (Welch), calidad (clipping y ruido de red) y si el
   músculo está **activo**: RMS > max(mediana de reposo + 3·SD robusta, 3 × mediana).
3. **Línea base**: la mediana de RMS y MDF de los primeros 10 s **activos**.
4. **Índice de fatiga** (solo bloques activos):
   100 × promedio de [aumento del RMS, descenso de la MDF], cada uno entre 0 y 1.
5. **Cada 5 s**: media del RMS, mediana de la MDF y del índice.
6. **Alerta**: índice ≥ porcentaje de alerta **y** RMS ≥ base +20 % **y** MDF ≤ base −15 %
   **y** en los últimos 20 s el RMS sube y la MDF baja con p < 0,05 (regresión lineal).

## Conexión con el BITalino

El paquete `bitalino` abre un puerto serie si el nombre empieza con `COM` (Windows) o
`/dev/` (macOS); con una dirección MAC usa PyBluez. La app siempre usa el puerto serie.

Si el equipo no responde, el paquete se queda esperando para siempre (y su opción
`timeout` ocupa un núcleo entero). Por eso `conexion.BitalinoConLimite` hace cada
operación en un hilo con un tiempo máximo y cierra el puerto si se pasa.
**Detectar automáticamente** prueba el último puerto que funcionó, el `PUERTO` del
notebook y los detectados (macOS: `/dev/tty.*bitalino*`; Windows: COM de Bluetooth).

Si la conexión se corta durante la grabación, la grabación termina (los CSV quedan
guardados) y la ventana muestra el error. Hay que reconectar y comenzar otra.

## Pruebas

```bash
.venv/bin/python -m pytest -q
```

74 pruebas, sin hardware y en ~30 s:

- equivalencia con el notebook (ver arriba) y valores de configuración;
- alerta: no se repite con el pop-up abierto, se rearma después de cerrarlo;
- grabación: numeración de los CSV, Detener, máximo de 24 h, errores de lectura;
- la Api de la ventana completa: conectar (simulador y BITalino imitado), calibrar,
  grabar, alerta con pop-up, porcentaje de alerta;
- conexión: detección de puertos, tiempos límite y errores en palabras simples.

## Observaciones sobre el notebook 4.2

No se cambiaron en el notebook; quedan anotadas para el grupo.

- `RMS_INCREASE_THRESHOLD`, `MDF_DECREASE_THRESHOLD`, `FATIGUE_ALERT_THRESHOLD` y
  `MAINS_AMPLITUDE_LIMIT_COUNTS` están marcados en el notebook como provisionales o sin
  validar.
- El simulador vuelve a empezar en cada `start()`. Por eso, después de calibrar, cada
  grabación simulada también empieza con 15 s de reposo; el índice aparece después.
- Si la calibración no es PASS, todos los bloques llevan `REST_CHECK_WARN` en la columna
  de calidad.
- El CSV crudo guarda todas las muestras: con grabaciones largas ocupa ≈ 90 MB por hora
  (≈ 2 GB en 24 h).
- El boceto de la interfaz no traía la MVC ni la señal cruda: quedaron en la pestaña
  Detalles.

## Versiones

- Python 3.10.11 (la del notebook), pywebview 6.2.1, numpy 2.2.6, scipy 1.15.3,
  bitalino 1.2.6, pyserial 3.5, pytest 9.2.0, PyInstaller 6.22.3 (solo para el `.exe`).
- En Linux pywebview usa Qt (`pip install "pywebview[qt]"`); la app se probó así.
