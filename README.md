# RSI Monitor — Grupo 2

Detector de fatiga muscular para personas que pasan mucho tiempo en el computador.
Usa un BITalino con 3 electrodos (sEMG por Bluetooth) y el código del grupo,
`Código_Bitalino_Python.py`, que **no se modifica**: la app lo lee con `ast` y toma de
ahí la clase `ProcesadorEMG` y las constantes (umbrales, tiempos, `SIM_*`). Si cambian
algo en el original, la app lo usa la próxima vez que se abre.

> La alerta es una señal de ayuda, **no un diagnóstico médico**.

## Qué hace

- **Encender / Apagar**: mide sin límite de tiempo, en un hilo aparte (la ventana no se
  congela). Al apagar se guarda el último intervalo y se detiene el BITalino.
- **Conexión automática**: busca el BITalino por Bluetooth, lo valida pidiéndole la
  versión y, si se corta, lo vuelve a buscar sin perder la línea base ni el CSV.
- **Gráficos y panel**: tendencias de RMS y MDF de los últimos `TREND_WINDOW_S` segundos
  y el mismo panel de información de `actualizar_panel_adquisicion()`.
- **Estado**: Desconectado · Buscando · Conectando · Calibrando línea base · Midiendo ·
  En descanso · Riesgo de fatiga: descanso pendiente · Error.
- **Alerta de fatiga**: ventana "Riesgo de fatiga muscular, descanse X minutos" (X = 10
  por defecto), siempre encima, que no se cierra con la X ni con Escape ni se minimiza;
  solo tiene **Aceptar**. También avisa con una notificación y el ícono se pone rojo.
  No se repite mientras está pendiente.
- **Descansos**: Aceptar inicia el descanso con cuenta regresiva ("Terminar antes" y
  aviso al final). También se pueden tomar descansos por cuenta propia, con plantillas
  (crear, editar, borrar) o con una duración libre. Durante el descanso no se evalúa la
  fatiga; al terminar, la alerta se rearma (la línea base se mantiene). El historial y el
  total del día están en la pestaña **Descansos**.
- **Reloj de uso**: tiempo medido hoy y en la sesión actual. Corre solo mientras se mide
  y se pausa en los descansos. Es solo informativo.
- **Bandeja del sistema**: cerrar la ventana deja la app funcionando en la bandeja
  (Windows: junto al reloj; macOS: barra de menús). Menú: Mostrar, Encender/Apagar,
  Tomar descanso, Salir.
- **Ajustes**: los 5 parámetros de detección (con el valor del original y "Restaurar"),
  umbrales `SIM_*` para la simulación, puerto manual, minutos de descanso e iniciar con
  el sistema.
- **Simulación**: sin BITalino, con los escenarios `normal` y `fatigue_test` del original,
  a velocidad ×1 o ×10.

## Estructura

```
RSI_Monitor/
├─ Código_Bitalino_Python.py   el código original (no se toca)
├─ bitalino_codigo (Ver 3.0).ipynb, RSI_Monitor_Entrega2.pptx   originales del grupo
├─ app.py                      punto de entrada (argumentos, modo sin ventana)
├─ nucleo/                     sin interfaz: todo lo que mide y decide
│  ├─ cargador_original.py     lee el original con ast (ProcesadorEMG + constantes)
│  ├─ regla_fatiga.py          réplica de cerrar_intervalo() (línea base, racha, alerta)
│  ├─ simulador.py             BITalino simulado (réplica de la celda de simulación)
│  ├─ adquisicion.py           ciclo de medición, CSV y el hilo (QThread)
│  ├─ conexion.py              búsqueda de puertos, límite de tiempo y reconexión
│  ├─ configuracion.py         config.json
│  └─ rutas.py                 dónde se guardan los datos y dónde está el original
├─ uso/                        reloj de uso, descansos, plantillas e historial
├─ ui/                         ventanas (solo dibujan y avisan los clics)
│  ├─ aplicacion.py            coordinador: conecta el hilo con las ventanas
│  ├─ ventana_principal.py, dialogo_alerta.py, cuenta_regresiva.py,
│  └─ pestana_descansos.py, dialogo_ajustes.py, bandeja.py
├─ sistema/autoinicio.py       iniciar con el sistema (Windows y macOS)
├─ recursos/                   íconos para el ejecutable
├─ herramientas/crear_iconos.py  vuelve a crear los íconos si cambia el dibujo
├─ tests/                      pruebas (sin hardware y sin ventanas)
├─ config.ejemplo.json         valores por defecto de config.json
└─ RSI_Monitor.spec            receta de PyInstaller
```

Cada archivo empieza con un comentario que explica qué hace y qué se puede editar ahí.

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

Windows (PowerShell, con el instalador 3.10.11 de python.org):

```powershell
py -3.10 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`PySide6` está fijado en la versión 6.11.3: con la 6.12.0 la app se cae al cerrarse si
el hilo de medición alcanzó a enviar datos (lo reproducimos con un programa mínimo, sin
nuestro código). No la suban sin probar antes.

## Usar la app

```bash
python app.py            # con el BITalino
python app.py --sim      # en modo simulación
```

1. Emparejen el BITalino por Bluetooth en el sistema (una sola vez; clave habitual
   `1234`).
2. Elijan el modo (**BITalino** o **Simulación**; en simulación, también el escenario y la
   velocidad) y aprieten **Encender**.
3. Los primeros segundos se calibra la línea base: mantengan la postura y el ritmo de
   trabajo normales. Después se muestran los valores de la línea base.
4. Si aparece la alerta, aprieten **Aceptar** y descansen. La cuenta regresiva avisa al
   terminar.

Con `--umbrales-sim` (o activando la opción en Ajustes) la simulación usa los umbrales
`SIM_*` del original, con los que `fatigue_test` dispara la alerta a los ~17 s de señal
(a ×10, en menos de 2 s). Sirve para probar todo el flujo de la alerta sin hardware.

Para cerrar la app del todo: **Salir** en el menú del ícono de la bandeja o en el menú
**RSI Monitor** de la ventana. La X solo la esconde.

### Dónde quedan los datos

En `datos/`, junto a `app.py` (o junto al `.exe`):

| Archivo | Contenido |
|---|---|
| `EMG_features_AAAA-MM-DD_HH-MM-SS.csv` | uno por sesión, con las columnas del original (`Time (s)`, `Mean RMS (ADC)`, `Median MDF (Hz)`). En simulación: `EMG_simulated_features_…` |
| `descansos.json` | historial: inicio, fin, duración planeada y real, origen (`fatiga`/`manual`), completado |
| `uso_diario.json` | segundos medidos por día |

Si junto al ejecutable no se puede escribir (por ejemplo, en `Archivos de programa`), se
usa `%APPDATA%\RSI_Monitor` en Windows. En macOS, la `.app` siempre usa
`~/Library/Application Support/RSI_Monitor`. El menú **RSI Monitor → Abrir carpeta de
datos** abre la carpeta correcta.

## Probar sin hardware y sin ventana

```bash
python app.py --sim --headless --velocidad 10 --escenario fatigue_test --umbrales-sim --duracion 60
```

Imprime los estados (Conectando → Calibrando línea base → Midiendo) y la alerta. Opciones:
`--velocidad 0` (lo más rápido posible), `--escenario normal`, `--detalle` (imprime cada
intervalo); sin `--duracion` mide hasta Ctrl+C. Sin `--sim` (`python app.py --headless`)
busca el BITalino real y mide en la consola.

## Pruebas

```bash
python -m pytest -q
```

No necesitan el BITalino ni abren ventanas. Revisan:

- el cargador: toma la clase y las constantes del original, ignora las líneas `%` y ve
  los cambios del original;
- la equivalencia con el original: ejecutan la función `cerrar_intervalo()` y la celda de
  simulación **reales** del original (con gráficos falsos) y comparan con la app;
- los escenarios: `fatigue_test` alerta con los umbrales `SIM_*` y `normal` no alerta;
- el reloj de uso (tiempo simulado, pausa en descansos, cambio de día);
- el flujo alerta → pendiente → Aceptar → descanso → rearme, con la simulación;
- las plantillas, el historial, la configuración, el inicio con el sistema (con un
  registro de Windows y un LaunchAgent imitados) y la conexión (puertos y BITalino
  imitados: orden de los puertos, filtro BTHENUM, límite de tiempo, espera creciente y
  reconexión).

## Configuración (`config.json`)

La primera vez se crea copiando `config.ejemplo.json`. Casi todo se cambia desde
**Ajustes**, pero también se puede editar a mano con la app cerrada.

| Sección | Clave | Qué es |
|---|---|---|
| `parametros_deteccion` | `TREND_INTERVAL_S`, `BASELINE_DURATION_S`, `ALERT_PERSISTENCE_S`, `RMS_INCREASE_THRESHOLD`, `MDF_DECREASE_THRESHOLD` | `null` = usar el valor del original. Un número tiene prioridad |
| `simulacion` | `activa`, `escenario`, `velocidad`, `usar_umbrales_sim` | modo de la ventana; `escenario: null` = `SIM_SCENARIO` |
| `conexion` | `puerto_manual` | `null` = buscar solo; ej. `"COM5"` o `"/dev/tty.BITalino-XX-XX-DevB"` |
| | `ultimo_puerto` | el último que funcionó (se prueba primero) |
| | `timeout_s`, `espera_inicial_s`, `espera_maxima_s` | límite por intento y espera entre búsquedas (1, 2, 4… hasta el máximo) |
| `descansos` | `duracion_fatiga_min`, `plantillas` | minutos del descanso por fatiga y plantillas |
| `reloj_uso` | `guardar_cada_s` | cada cuánto se guarda el reloj de uso |
| `sistema` | `iniciar_con_el_sistema` | `true` por defecto |

Si `config.json` queda dañado, se guarda como `config.json.dañado` y se crea uno nuevo.

## Conexión con el BITalino

La app prueba, en orden: el puerto manual (si hay, solo ese), el último que funcionó, el
`PUERTO` del original y los que encuentra:

- **macOS**: `/dev/tty.*` con "bitalino" en el nombre (por ejemplo
  `/dev/tty.BITalino-XX-XX-DevB`).
- **Windows**: los puertos COM de Bluetooth (los que tienen `BTHENUM` en su
  identificador). Windows crea dos por equipo; se prueban los dos.

Cada intento tiene un límite de `timeout_s` segundos. El paquete `bitalino`, en modo
bloqueante, esperaría para siempre si el equipo no responde, y con su opción `timeout`
ocupa un núcleo entero de la CPU. Por eso cada operación corre en un hilo auxiliar con
límite de tiempo y, si se pasa, se cierra el puerto.

Si no lo encuentra: revisen que esté emparejado y encendido, o elijan el puerto en
**Ajustes → Puerto** (en Windows: Configuración → Bluetooth → Más opciones → Puertos COM,
el puerto "Saliente").

## Generar el ejecutable

PyInstaller no hace ejecutables para otro sistema: el `.exe` se genera en Windows y la
`.app` en macOS, con el entorno ya preparado.

### Windows (.exe)

```powershell
.venv\Scripts\activate
pyinstaller RSI_Monitor.spec
```

Queda `dist\RSI_Monitor.exe` (un solo archivo, sin consola). La primera vez que se abre
demora unos segundos porque se descomprime. Si prefieren una carpeta (abre más rápido y
el antivirus la revisa menos), cambien `UN_SOLO_ARCHIVO = False` en `RSI_Monitor.spec`.

### macOS (.app)

```bash
source .venv/bin/activate
pyinstaller RSI_Monitor.spec
```

Queda `dist/RSI_Monitor.app`. Muévanla a **Aplicaciones** antes de abrirla (así funciona
bien el inicio con el sistema).

### Detalles del ejecutable

- `Código_Bitalino_Python.py` y `config.ejemplo.json` van dentro. Si se pone una copia
  del original **junto al `.exe`** (o junto a la `.app`), la app usa esa copia: así se
  pueden cambiar umbrales sin volver a empaquetar.
- **Iniciar con el sistema** se aplica solo con la app empaquetada: en Windows queda en
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, y en macOS en
  `~/Library/LaunchAgents/cl.grupo2.rsimonitor.plist`. Se abre con `--minimizado`
  (solo en la bandeja, con la medición apagada). Corriendo desde el código solo se
  registra si se cambia la opción en Ajustes.
- Los íconos están en `recursos/`. Si cambian el dibujo en `ui/bandeja.py`, corran
  `python herramientas/crear_iconos.py`.

## Permisos en macOS

- **Bluetooth**: la primera vez que se conecta, macOS pide permiso (Ajustes del Sistema →
  Privacidad y seguridad → Bluetooth). Corriendo desde el código, el permiso se le da a
  la Terminal (o al editor) desde donde se abre.
- **Notificaciones**: macOS pregunta la primera vez; si no aparecen, revisen Ajustes del
  Sistema → Notificaciones → RSI Monitor. La alerta igual aparece como ventana.
- **App sin firmar**: la primera vez, clic derecho → **Abrir** → **Abrir**. Si dice que
  está "dañada", ejecuten `xattr -dr com.apple.quarantine /Applications/RSI_Monitor.app`.
- **Inicio de sesión**: macOS avisa "Se agregó un ítem en segundo plano"; se puede
  revisar en Ajustes del Sistema → General → Ítems de inicio.

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
- El original alerta una sola vez por sesión. La app agrega el rearme después de cada
  descanso (pedido para la app); la regla de detección es la misma.

## Paquete `bitalino` 1.2.6 (revisado)

- Por puerto serie (`COMx` en Windows, `/dev/tty.*` en macOS) usa `pyserial` y no necesita
  PyBluez. `import bluetooth` solo se usa al conectar por dirección MAC en Windows/Linux;
  en macOS la MAC no está soportada. Por eso el ejecutable no incluye `bluetooth`.
- Al crear `BITalino(puerto)` ya pide la versión (`version()`); la app además la vuelve a
  pedir con límite de tiempo para validar el puerto.
- `pip install bitalino` instala `PyBluez-bitalino`, que tiene versión lista para
  Python 3.10 en Windows (no hay que compilar nada).

## Lo que no se pudo probar en el equipo donde se programó (Linux)

Todo se probó con la simulación, en Linux, con las ventanas dibujadas sin pantalla. No se
probaron: el BITalino físico, los puertos `BTHENUM` reales, el `.exe` y la `.app` (sí se
generó y probó el ejecutable de Linux con el mismo `RSI_Monitor.spec`), el registro de
Windows y el LaunchAgent reales (probados con imitaciones), ni las notificaciones y la
bandeja de Windows y macOS. Antes de la entrega conviene revisar en cada sistema:

1. `python -m pytest -q` pasa.
2. `python app.py --sim --umbrales-sim`, ×10: alerta → Aceptar → cuenta regresiva →
   "Terminar antes" → vuelve a alertar.
3. Con el BITalino: Encender, ver la calibración y los gráficos; apagar el BITalino a
   mitad de la medición y ver que se reconecta solo al encenderlo de nuevo.
4. El ejecutable abre, queda en la bandeja al cerrar la ventana y sale con **Salir**.
