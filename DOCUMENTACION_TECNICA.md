# RSI Monitor — Documentación técnica

Este documento es para quien quiera entender o cambiar el código. Para usar la app,
basta con el [README](README.md).

## Cómo usa la app el código original

La detección usa el código del grupo, `Código_Bitalino_Python.py`. La app no lo
modifica nunca: lo lee cada vez que se abre, así que si cambian un umbral ahí, la app
lo usa. Con el programa empaquetado, basta con poner una copia del original junto al
`.exe` o a la `.app` para cambiar umbrales sin volver a crearlo.

La app lee el original como texto con `ast`:

- toma la clase `ProcesadorEMG` y los imports que esa clase necesita;
- lee las constantes (umbrales, tiempos, `SIM_*`) sin ejecutar el resto del archivo;
- ignora las líneas que empiezan con `%` (comandos del notebook).

La regla de fatiga (`cerrar_intervalo()`) y el generador de la simulación están
copiados en `nucleo/regla_fatiga.py` y `nucleo/simulador.py`, sin cambiar la
matemática. Cada parte indica de qué líneas del original viene.

La regla original alerta una sola vez por sesión. La app agrega dos cosas:

- después de cada descanso, la alerta vuelve a estar disponible (la línea base se mantiene);
- durante un descanso no se evalúa la fatiga.

## Estructura

```
RSI_Monitor/
├─ Código_Bitalino_Python.py   el código original (no se toca)
├─ bitalino_codigo (Ver 3.0).ipynb, RSI_Monitor_Entrega2.pptx   originales del grupo
├─ app.py                      punto de entrada (argumentos, modo sin ventana)
├─ instalar.bat                instalador de Windows
├─ nucleo/                     lo que mide y decide; no tiene ventanas
│  ├─ cargador_original.py     lee el original con ast
│  ├─ regla_fatiga.py          línea base, racha y alerta
│  ├─ simulador.py             BITalino simulado
│  ├─ adquisicion.py           ciclo de medición, CSV y el hilo de medición
│  ├─ conexion.py              búsqueda del BITalino y reconexión
│  ├─ configuracion.py         config.json
│  └─ rutas.py                 dónde se guardan los datos y dónde está el original
├─ uso/                        reloj de uso, descansos, plantillas e historial
├─ ui/                         ventanas: solo dibujan y avisan los clics
│  ├─ aplicacion.py            conecta el hilo de medición con las ventanas
│  └─ ventana_principal.py, dialogo_alerta.py, cuenta_regresiva.py,
│     pestana_descansos.py, dialogo_ajustes.py, bandeja.py
├─ sistema/autoinicio.py       iniciar con el sistema (Windows y macOS)
├─ recursos/                   íconos del programa
├─ herramientas/                crear_iconos.py (íconos) y crear_accesos_directos.py (instalador)
├─ tests/                      pruebas
├─ config.ejemplo.json         valores por defecto de config.json
└─ RSI_Monitor.spec            receta para crear el .exe y la .app
```

Cada archivo empieza con un comentario que explica qué hace y qué se puede editar ahí.

## Pruebas

```bash
python -m pytest -q
```

No necesitan el BITalino y no abren ventanas. Revisan:

- que el cargador lea bien la clase y las constantes del original, y vea sus cambios;
- que la app dé los mismos resultados que el original. Para eso ejecutan la función
  `cerrar_intervalo()` y la celda de simulación **del original** y comparan;
- que `fatigue_test` alerte con los umbrales `SIM_*` y que `normal` no alerte;
- el reloj de uso: pausa en descansos y cambio de día;
- el flujo completo: alerta → Aceptar → descanso → la alerta vuelve a estar disponible;
- las plantillas, el historial y la configuración;
- el inicio con el sistema, con un registro de Windows y un LaunchAgent de macOS falsos;
- la conexión, con puertos y BITalino falsos: orden de búsqueda, reintentos y reconexión.

## Probar sin ventana

```bash
python app.py --sim --headless --velocidad 10 --escenario fatigue_test --umbrales-sim --duracion 60
```

Imprime los estados y la alerta en la consola. Otras opciones:

- `--velocidad 0`: lo más rápido posible;
- `--escenario normal`;
- `--detalle`: imprime cada intervalo;
- sin `--duracion`: mide hasta Ctrl+C;
- sin `--sim`: usa el BITalino real.

## Configuración (`config.json`)

La primera vez se crea copiando `config.ejemplo.json`. Si se edita a mano, que sea con
la app cerrada. Si el archivo se daña, se guarda como `config.json.dañado` y se crea uno nuevo.

| Sección | Clave | Qué es |
|---|---|---|
| `parametros_deteccion` | `TREND_INTERVAL_S`, `BASELINE_DURATION_S`, `ALERT_PERSISTENCE_S`, `RMS_INCREASE_THRESHOLD`, `MDF_DECREASE_THRESHOLD` | `null` = usar el valor del original. Un número tiene prioridad |
| `simulacion` | `activa`, `escenario`, `velocidad`, `usar_umbrales_sim` | modo de la ventana. `escenario: null` = `SIM_SCENARIO` del original |
| `conexion` | `puerto_manual` | `null` = buscar solo. Ejemplo: `"COM5"` |
| | `ultimo_puerto` | el último que funcionó; se prueba primero |
| | `timeout_s` | segundos máximos por intento |
| | `espera_inicial_s`, `espera_maxima_s` | espera entre búsquedas: 1, 2, 4… segundos hasta el máximo |
| `descansos` | `duracion_fatiga_min`, `plantillas` | minutos del descanso por fatiga y plantillas |
| `reloj_uso` | `guardar_cada_s` | cada cuánto se guarda el reloj de uso |
| `sistema` | `iniciar_con_el_sistema` | `true` por defecto |

## Dónde se guardan los datos

`config.json` y la carpeta `datos/` van junto a `app.py` o junto al `.exe`. Hay dos excepciones:

- si ahí no se puede escribir (por ejemplo, en Archivos de programa), van a `%APPDATA%\RSI_Monitor`;
- en macOS, la `.app` siempre usa `~/Library/Application Support/RSI_Monitor`.

Los CSV tienen las mismas columnas que el original: `Time (s)`, `Mean RMS (ADC)` y
`Median MDF (Hz)`. En simulación se llaman `EMG_simulated_features_…`.

## Conexión con el BITalino

La app prueba los puertos en este orden:

1. el puerto manual de los ajustes (si hay uno, solo ese);
2. el último puerto que funcionó;
3. el `PUERTO` del original;
4. los que encuentra sola: en macOS, `/dev/tty.*` con "bitalino" en el nombre; en
   Windows, los puertos COM de Bluetooth.

Cada puerto se valida pidiéndole la versión al BITalino. Si ninguno responde, espera y
vuelve a buscar.

El paquete `bitalino` tiene un problema: si el equipo no responde, se queda esperando
para siempre, y su opción `timeout` usa un núcleo entero del procesador mientras espera.
Por eso la app hace cada operación en un hilo aparte, con un tiempo máximo. Si se pasa
del tiempo, o si el usuario aprieta Apagar o Salir, cierra el puerto.

Si se pierde la conexión durante la medición, la app la recupera sin perder la línea
base ni el CSV.

## Versiones

- **Python 3.10.11.** Para esa versión hay `PyBluez-bitalino` listo para Windows, así
  que no hay que compilar nada.
- **PySide6 6.11.3.** La 6.12.0 hace que la app se caiga al cerrarse después de medir.
  Lo comprobamos con un programa mínimo, sin nuestro código. No la suban sin probar.
- La app se conecta por puerto serie, así que el programa empaquetado no incluye el
  módulo `bluetooth`. Ese módulo solo se usa para conectar por dirección MAC.

## El programa empaquetado

- `RSI_Monitor.spec` crea un solo `.exe` en Windows. Para crear una carpeta en su lugar
  (abre más rápido), cambien `UN_SOLO_ARCHIVO = False`.
- En macOS siempre crea la `.app`, con el permiso de Bluetooth ya declarado.
- Incluye el original y `config.ejemplo.json`. Una copia del original junto al
  programa tiene prioridad.
- **Iniciar con el sistema** solo se activa sola con el programa empaquetado. En
  Windows se guarda en `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. En macOS,
  en `~/Library/LaunchAgents/cl.grupo2.rsimonitor.plist`. Al abrirse así, la app queda
  en la bandeja con la medición apagada. Si se corre desde el código, solo se registra
  al cambiar la opción en Ajustes.
- macOS muestra el aviso "Se agregó un ítem en segundo plano". Se revisa en Ajustes del
  Sistema → General → Ítems de inicio.
- Si cambian el dibujo del ícono en `ui/bandeja.py`, ejecuten
  `python herramientas/crear_iconos.py`.

## El instalador de Windows

`instalar.bat`:

1. busca un Python 3.10 de 64 bits (con `py -3.10-64` o en las carpetas de siempre). Si
   no hay, lo instala con `winget install --id Python.Python.3.10 --scope user`. Si
   tampoco hay winget, abre la página de Python 3.10.11;
2. crea `.venv` (o lo vuelve a crear si no es 3.10) e instala `requirements.txt`;
3. crea los accesos directos a `.venv\Scripts\pythonw.exe app.py` con
   `herramientas/crear_accesos_directos.py`;
4. abre la app (`instalar.bat /sinabrir` para no abrirla).

La primera versión era un script de PowerShell que descargaba el instalador de Python,
lo ejecutaba en silencio y activaba el inicio con el sistema. Windows Defender lo marcó
como troyano: hace lo mismo que muchos virus. Por eso `instalar.bat` no usa PowerShell,
no descarga programas por su cuenta y no toca el inicio con el sistema (eso queda en
Ajustes). Solo los accesos directos usan PowerShell, desde Python, porque Python no trae
cómo crearlos. `tests/test_instalador.py` revisa todo eso.

El `.bat` va en ASCII y con CRLF; `.gitattributes` lo guarda tal cual.

## Resultados de la simulación

Con 1000 s de señal simulada:

| Escenario | Umbrales normales (+20 % / −15 % / 5 s) | Umbrales `SIM_*` (+5 % / −1 % / 1 s) |
|---|---|---|
| `fatigue_test` | **no alerta** | alerta a los ~17,5 s |
| `normal` | no alerta | **alerta a los ~381 s** (falsa alarma) |

- Con los umbrales normales, `fatigue_test` nunca alerta. La MDF baja cerca de 40 %,
  pero el RMS sube solo cerca de 3 % y el umbral pide 20 %.
- Con los umbrales `SIM_*`, la condición es tan fácil de cumplir que la señal `normal`
  también termina alertando por azar.

## Observaciones sobre el código original

No se corrigieron; quedan anotadas para el grupo.

- `TREND_INTERVAL_S = 1` tiene el comentario "Un punto de resumen cada 10 segundos".
  El comentario no coincide con el valor.
- El comentario de `ALERT_PERSISTENCE_S` dice "mantener la alerta". En realidad es el
  tiempo que tiene que durar el patrón para que salga la alerta.
- `ax_mdf.set_xlim(0, DURACION)` usa otro límite que `ax_rms`. Después ambos se reemplazan.
- La presentación dice pasabanda de 20–450 Hz y 30 intervalos para la línea base y la
  persistencia. El código usa 25–400 Hz, 5 s y 5 s. La app usa los valores del código.
- En la simulación, la rampa de `fatigue_test` empieza al segundo 1
  (`SIM_BASELINE_DURATION_S`), aunque se usen los umbrales normales, cuya línea base
  dura 5 s. Así, la línea base se mide con la rampa ya empezada.

## Antes de entregar

La app se programó y probó en Linux con la simulación. Todavía no se probó con el
BITalino real, ni el `.exe` en Windows, ni la `.app` en macOS. En cada sistema, revisen:

1. `python -m pytest -q` pasa.
2. `python app.py --sim --umbrales-sim` a ×10: alerta → Aceptar → cuenta regresiva →
   Terminar antes → vuelve a alertar.
3. Con el BITalino: Encender, ver la calibración y los gráficos. Apagar el BITalino a
   mitad de la medición y ver que la app se reconecta al encenderlo otra vez.
4. `instalar.bat` en un Windows sin Python: instala, abre la app y deja los accesos directos.
5. El programa empaquetado abre, queda en la bandeja al cerrar la ventana y se cierra con **Salir**.
6. Las notificaciones aparecen.
