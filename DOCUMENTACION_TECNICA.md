# RSI Monitor — Documentación técnica

Este documento es para quien quiera entender o cambiar el código. Para usar la app,
basta con el [README](README.md).

## Cómo está armada

```
navegador (Next.js, solo muestra)  ──REST /api──▶  FastAPI (backend/app/main.py)
          ▲                                               │
          └──────────── WebSocket /ws ◀── Servicio ◀── hilo de medición ◀── BITalino
                                     (servicio.py)    (SesionMedicion)     (real o simulado)
```

- **Un solo proceso y un solo puerto.** Next.js se compila como página estática
  (`output: "export"`) y FastAPI la sirve desde `backend/estaticos/`.
- **El frontend no procesa la señal.** Recibe datos ya calculados y envía acciones.
- **La lectura del BITalino es bloqueante**, así que corre en un hilo aparte. Cada aviso
  del hilo pasa al bucle de asyncio con `loop.call_soon_threadsafe()`: todo el estado se
  cambia en un solo hilo y FastAPI nunca se bloquea. Por eso las rutas son `async def`.
- **Todo el estado vive en el backend**: la alerta pendiente, el descanso, el reloj y los
  puntos de tendencia. Al conectarse, cada pestaña recibe una foto completa.

## Estructura

```
RSI_Monitor/
├─ Código_Bitalino_Python.py   el código original (no se toca)
├─ bitalino_codigo (Ver 3.0).ipynb, RSI_Monitor_Entrega2.pptx   originales del grupo
├─ compilar.py                 instala, compila, prueba y levanta la app
├─ Dockerfile, .dockerignore   imagen en modo simulación
├─ backend/
│  ├─ requirements.txt, config.ejemplo.json, pytest.ini
│  ├─ app/
│  │  ├─ main.py               rutas REST, /ws, página estática y línea de comandos
│  │  ├─ servicio.py           une todo: hilo de medición, conexión, alerta, descansos, reloj
│  │  ├─ estado.py             estado en memoria y búferes circulares
│  │  ├─ mensajes.py           formato de los mensajes (Pydantic)
│  │  ├─ almacenamiento.py     rutas, config.json y descansos.json
│  │  ├─ textos.py             panel de información, texto de la alerta y de la calibración
│  │  ├─ sin_navegador.py      modo --headless
│  │  ├─ nucleo/
│  │  │  ├─ cargador_original.py  lee el original con ast
│  │  │  ├─ regla_fatiga.py       línea base, racha y alerta (réplica de cerrar_intervalo)
│  │  │  ├─ simulador.py          BITalino simulado (réplica de la celda de simulación)
│  │  │  ├─ adquisicion.py        ciclo de medición y CSV
│  │  │  └─ conexion.py           búsqueda del BITalino, límites de tiempo y reconexión
│  │  └─ uso/
│  │     ├─ reloj_uso.py          tiempo de uso de hoy y de la sesión
│  │     └─ descansos.py          alerta pendiente, descansos, plantillas e historial
│  ├─ estaticos/               página compilada (la crea compilar.py; no va en git)
│  └─ tests/
├─ frontend/
│  ├─ app/page.tsx             la página: useReducer + WebSocket + acciones REST
│  ├─ components/              un componente por panel, cada uno con su .module.css
│  └─ lib/                     tipos.ts, api.ts, useWebSocket.ts, reductor.ts, ...
└─ datos/                      config.json, descansos.json y CSV (no va en git)
```

Cada archivo empieza con un comentario que explica qué hace y qué se puede editar ahí.

Diferencias con la estructura que se pidió:

- `servicio.py` une todas las piezas, para que `main.py` quede solo con las rutas.
- `textos.py` arma el panel de información y los textos de la alerta. Así el frontend
  solo los muestra y se pueden probar con pytest.
- `sin_navegador.py` tiene el modo `--headless` aparte de las rutas.
- `compilar.py` reemplaza a `compilar.ipynb`: el grupo pidió no mantener el formato de
  notebook, y un script es más fácil de mantener (no guarda resultados en git).
- En el frontend, `lib/reductor.ts` (cómo cambia la pantalla con cada mensaje),
  `lib/notificaciones.ts`, `lib/useAvisoPestana.ts` (título y favicon de alerta),
  `lib/formato.ts` y `components/Notificaciones.tsx`.

## Cómo usa la app el código original

La app no modifica nunca `Código_Bitalino_Python.py`. Lo lee cada vez que arranca, así
que si cambian un umbral o un filtro ahí, la app lo usa sin tocar nada más.

`nucleo/cargador_original.py` lo lee como texto con `ast`:

- ignora las líneas que empiezan con `%` (comandos del notebook);
- extrae y ejecuta solo la clase `ProcesadorEMG` con los imports que usa;
- lee las constantes simples con `ast.literal_eval` (`CANAL`, `PERIODO`, `N`, umbrales,
  `SIM_*`...), sin ejecutar el resto del archivo.

La regla de fatiga (`cerrar_intervalo()`) y el generador de la simulación están mezclados
con matplotlib y Jupyter, así que están copiados en `nucleo/regla_fatiga.py` y
`nucleo/simulador.py` sin cambiar la matemática. Cada parte dice de qué líneas viene.
Las pruebas ejecutan el código **del original** y comparan los resultados.

Cambios pedidos para la app (no tocan la matemática):

- la medición dura hasta Apagar, no `DURACION = 120` s;
- un CSV por sesión, con fecha y hora en el nombre;
- después de cada descanso la alerta se rearma (el original alerta una vez por sesión);
  la línea base se mantiene;
- durante un descanso no se evalúa la fatiga;
- el simulador entrega las muestras a ritmo real, con velocidad ×1 o ×10.

## Configuración (`datos/config.json`)

La primera vez se crea copiando `backend/config.ejemplo.json`. Si el ejemplo trae claves
nuevas, se agregan solas. Si el archivo se daña, se guarda como `config.json.dañado`.

| Sección | Clave | Qué es |
|---|---|---|
| `parametros_deteccion` | `TREND_INTERVAL_S`, `BASELINE_DURATION_S`, `ALERT_PERSISTENCE_S`, `RMS_INCREASE_THRESHOLD`, `MDF_DECREASE_THRESHOLD` | `null` = valor del original. Un número tiene prioridad |
| `simulacion` | `escenario`, `velocidad`, `velocidades`, `usar_umbrales_sim` | lo último elegido en la página. `escenario: null` = `SIM_SCENARIO` |
| `conexion` | `puerto_manual` | `null` = buscar solo. Si tiene un puerto, solo se prueba ese |
| | `ultimo_puerto` | el último que funcionó; se prueba primero |
| | `timeout_s` | segundos máximos por intento |
| | `espera_inicial_s`, `espera_maxima_s` | espera entre búsquedas: 1, 2, 4... s hasta el máximo |
| `descansos` | `duracion_fatiga_min` | minutos del descanso por fatiga |
| | `plantillas_iniciales` | plantillas con que se crea `descansos.json` |
| `reloj_uso` | `guardar_cada_s` | cada cuánto se guarda el reloj de uso |
| `memoria` | `max_puntos_tendencia`, `max_bloques` | tamaño de los búferes en memoria (el CSV guarda todo) |
| `servidor` | `host`, `puerto`, `origenes_desarrollo`, `max_mensajes_en_cola` | dónde escucha y quién puede usar la API |

## Conexión con el BITalino

El paquete `bitalino` (1.2.6) se conecta **por puerto serie** si el nombre empieza con
`COM` (Windows) o `/dev/` (macOS y Linux). Solo usa PyBluez si se le da una dirección
MAC, y en macOS la MAC no está permitida. La app siempre usa el puerto serie.

Orden en que se prueban los puertos:

1. el puerto elegido en el panel de conexión (si se eligió uno mientras busca);
2. el `puerto_manual` de `config.json` (si hay uno, solo ese);
3. el último puerto que funcionó;
4. el `PUERTO` del original;
5. los que encuentra sola: en macOS, `/dev/tty.*` con "bitalino" en el nombre; en
   Windows, los COM de Bluetooth (`BTHENUM`), con el "entrante" al final.

Cada puerto se valida pidiéndole la versión al BITalino.

El paquete tiene un problema: si el equipo no responde, se queda esperando para siempre,
y su opción `timeout` usa un núcleo entero del procesador mientras espera. Por eso cada
operación corre en un hilo auxiliar con un tiempo máximo (`ejecutar_con_limite`). Si se
pasa del tiempo, o si el usuario aprieta Apagar, se cierra el puerto.

- **Con la medición apagada**, Reconectar o Detectar automáticamente conectan en un hilo
  y dejan el BITalino listo: Encender usa esa misma conexión.
- **Si se corta midiendo**, la sesión busca sola con espera creciente, sin perder la
  línea base ni el CSV. Elegir un puerto en ese momento lo prueba primero y corta la espera.
- **En Docker** el modo real responde 409 y la página lo explica.

## Seguridad local

- El backend escucha solo en `127.0.0.1`. En Docker escucha en `0.0.0.0` dentro del
  contenedor, pero el puerto se publica solo en `127.0.0.1`.
- CORS permite solo `http://localhost:3000` (el frontend de desarrollo).
- Los `POST`/`PUT`/`DELETE` y el WebSocket rechazan otros `Origin`: así una página web
  cualquiera abierta en el navegador no puede manejar la app.

## Pruebas

```bash
cd backend && ../.venv/bin/python -m pytest -q
cd frontend && npm run tipos && npm run lint
```

No necesitan el BITalino. Revisan:

- que el cargador lea bien la clase y las constantes del original, y vea sus cambios;
- que la regla y la simulación den lo mismo que el código original;
- que `fatigue_test` alerte con los umbrales `SIM_*` y que `normal` no alerte;
- el flujo alerta → pendiente (sin duplicados) → Aceptar → descanso → rearme;
- el reloj de uso (con tiempo simulado), las plantillas y el historial;
- la API REST y el WebSocket con el `TestClient` de FastAPI;
- la conexión con puertos y un BITalino falsos: orden de búsqueda, espera creciente,
  Reconectar, Detectar y reconexión a mitad de la medición.

## Versiones

- **Python 3.10.11**, la del código original. Por eso `websockets` quedó en 16.1.1 (la 17
  ya no funciona con 3.10).
- **Next.js 16.4.2, React 19.2.9, Recharts 3.10.1, TypeScript 6.0.3.** Se usó Recharts
  porque lo sugería el pedido y alcanza para dos gráficos de líneas.
- **ESLint 9.39.5.** npm avisa que ya no tiene soporte, pero con ESLint 10 el plugin de
  React que trae `eslint-config-next` da conflictos de dependencias.
- `react-is` está porque Recharts la exige para instalarse.
- Starlette sugiere `httpx2` para el TestClient; `httpx` funciona y es lo que pide
  FastAPI (el aviso se oculta en `pytest.ini`).
- En Docker, `bitalino` se instala sin PyBluez (no se puede compilar en la imagen slim y
  solo sirve para conectar por MAC).

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
- Hay una versión más nueva del notebook (Ver 3.3) con otros valores (intervalo de 8 s,
  línea base y persistencia de 30 s) y otro simulador sin las constantes `SIM_*`. La app
  usa `Código_Bitalino_Python.py` (Ver 3.0). Si exportan la 3.3 a ese archivo, el
  cargador toma los umbrales nuevos, pero hay que agregarle las constantes `SIM_*` o
  adaptar `nucleo/simulador.py`.
