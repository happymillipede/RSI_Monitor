# RSI Monitor — Grupo 2

RSI Monitor avisa cuando un músculo muestra señales de fatiga mientras trabajan en el
computador. Usa un BITalino con 3 electrodos que mide sEMG por Bluetooth. Cuando detecta
fatiga, les pide que descansen unos minutos.

Es una app web **local**: corre en su computador y se abre en el navegador, en
http://localhost:8000. Nada sale del computador.

> La alerta es una ayuda. **No es un diagnóstico médico.**

## Contenido

1. [Empezar (sin el BITalino)](#empezar-sin-el-bitalino)
2. [Usar con el BITalino](#usar-con-el-bitalino)
3. [Lo que hace la app](#lo-que-hace-la-app)
4. [compilar.py](#compilarpy)
5. [Desarrollo: backend y frontend por separado](#desarrollo-backend-y-frontend-por-separado)
6. [Docker (solo simulación)](#docker-solo-simulación)
7. [Dónde quedan los datos](#dónde-quedan-los-datos)
8. [API REST y mensajes del WebSocket](#api-rest-y-mensajes-del-websocket)
9. [Pruebas](#pruebas)
10. [Problemas comunes](#problemas-comunes)

Los detalles técnicos (estructura del código, cómo se usa el código original, qué
observamos en él) están en [DOCUMENTACION_TECNICA.md](DOCUMENTACION_TECNICA.md).

## Empezar (sin el BITalino)

Necesitan:

- **Python 3.10.11**: [python.org](https://www.python.org/downloads/release/python-31011/)
  (en macOS también sirve `pyenv install 3.10.11`).
- **Node.js LTS** (trae npm): [nodejs.org](https://nodejs.org).
- **Git**.

```bash
git clone -b web https://github.com/happymillipede/RSI_Monitor.git
cd RSI_Monitor
python compilar.py
```

`compilar.py` revisa los requisitos, instala todo, compila la página, corre las pruebas,
levanta la app y abre el navegador. La primera vez demora unos minutos. En Windows, si
`python` no es la 3.10, usen `py -3.10 compilar.py`.

En la app:

1. En **Medición**, elijan **Simulación**, el escenario **fatigue_test**, la velocidad
   **×10** y marquen **Umbrales de prueba (SIM_\*)**.
2. Aprieten **Encender**. Primero dice "Calibrando línea base"; después aparecen los gráficos.
3. A los pocos segundos sale la alerta: "Riesgo de fatiga muscular, descanse 10 minutos".
4. Aprieten **Aceptar**. Empieza la cuenta regresiva del descanso.
5. **Terminar antes** vuelve a vigilar la fatiga (y la alerta vuelve a salir, porque la
   señal simulada sigue "fatigada").

Para detener la app: `python compilar.py detener`.

> Sin los umbrales de prueba, `fatigue_test` **no** da la alerta: la MDF baja cerca de
> 40 %, pero el RMS sube solo cerca de 3 % y el umbral normal pide 20 %.

## Usar con el BITalino

El BITalino necesita que la app corra **nativa** (con `compilar.py`), no en Docker.

1. Emparejen el BITalino por Bluetooth desde la configuración del computador (una sola
   vez; la clave suele ser `1234`).
2. Abran la app y, en **Medición**, elijan **BITalino**.
3. En **Conexión**, aprieten **Detectar automáticamente**. Si no lo encuentra, elijan el
   puerto en la lista y aprieten **Reconectar**:
   - macOS: `/dev/tty.BITalino-…`;
   - Windows: un `COMx` de Bluetooth. Windows crea dos por equipo; la app prueba los dos.
     En Configuración → Bluetooth → Más opciones de Bluetooth → Puertos COM, el que sirve
     es el "Saliente".
4. Cuando diga **Conectado**, aprieten **Encender** y mantengan la postura y el ritmo de
   trabajo normales durante la calibración.

Si el Bluetooth se corta, la app lo busca sola (cada vez espera un poco más) y sigue
midiendo sin perder la línea base. Si mientras busca eligen otro puerto y aprietan
**Reconectar**, prueba ese enseguida. La app recuerda el último puerto que funcionó.

## Lo que hace la app

- **Encender / Apagar**: mide hasta que la apaguen.
- **Panel en tiempo real** (solo midiendo): tendencia de RMS y de MDF (últimos 30 s) y el
  panel de información del código original. Arriba, el estado: Calibrando línea base /
  Midiendo / Riesgo de fatiga: descanso pendiente / En descanso.
- **Alerta de fatiga**: una ventana que cubre la pantalla y solo se cierra con
  **Aceptar**. También cambian el título de la pestaña y el ícono, y llega una
  notificación del sistema (activen las notificaciones con el botón de la página).
  Si recargan la página o abren otra pestaña, la alerta sigue ahí.
- **Descansos**: la cuenta regresiva empieza al aceptar la alerta. También pueden tomar
  un descanso cuando quieran, con una plantilla (ej. "Café, 15 min") o una duración libre.
  Durante un descanso no se evalúa la fatiga. Al terminar, la alerta vuelve a estar activa.
- **Historial**: los descansos anteriores y el total de hoy.
- **Reloj de uso**: cuánto tiempo midieron hoy y en esta sesión. Solo informa.
- **Ajustes**: umbrales, tiempos y duración del descanso. Al lado de cada uno se ve el
  valor del código original; **Restaurar valores por defecto** vuelve a ellos.

## compilar.py

Se ejecuta desde la carpeta `RSI_Monitor`. Funciona igual en macOS, Windows y Linux.

| Comando | Qué hace |
|---|---|
| `python compilar.py` | todo lo de abajo, del 1 al 6 |
| `python compilar.py verificar` | 1. revisa Python 3.10, Node.js y npm, y dice qué instalar si falta algo |
| `python compilar.py instalar` | 2. crea `.venv` e instala `backend/requirements.txt` |
| `python compilar.py compilar` | 3-4. `npm ci`, `npm run build` y copia la página a `backend/estaticos/` |
| `python compilar.py probar` | 5. `pytest`, `tsc --noEmit` y `eslint` |
| `python compilar.py iniciar` | 6. levanta la app en segundo plano y abre el navegador |
| `python compilar.py detener` | 7. detiene la app |
| `python compilar.py docker` | 8. imagen Docker en modo simulación (ver abajo) |

Arriba del archivo se configuran el puerto (`PUERTO = 8000`) y si el botón Encender
propone la simulación (`SIMULACION_POR_DEFECTO = True`). La salida de la app queda en
`datos/servidor.log`.

## Desarrollo: backend y frontend por separado

Para trabajar en la página con recarga automática, usen dos terminales:

```bash
# Terminal 1: backend en http://127.0.0.1:8000
cd backend
../.venv/bin/python -m app.main --sim        # Windows: ..\.venv\Scripts\python -m app.main --sim
```

```bash
# Terminal 2: frontend en http://localhost:3000
cd frontend
npm run dev
```

Abran http://localhost:3000. El frontend de desarrollo habla con el backend en
`127.0.0.1:8000` (ver `frontend/.env.development`); el backend solo le permite la entrada
a `http://localhost:3000` (CORS).

Otras formas de levantar el backend:

```bash
python -m app.main                          # BITalino real (Encender propone "BITalino")
python -m app.main --sim --headless --velocidad 10 --escenario fatigue_test --umbrales-sim --duracion 60
```

La segunda mide **sin navegador** e imprime los estados y la alerta en la consola.
Con `--velocidad 0` va lo más rápido posible. La API se puede probar a mano en
http://localhost:8000/docs.

## Docker (solo simulación)

> **Limitación importante:** Docker Desktop en Windows y macOS corre dentro de una máquina
> virtual y **no puede usar los puertos COM ni los `/dev/tty.*` del Bluetooth**. Dentro de
> Docker solo funciona la **simulación**: la página lo avisa y el modo BITalino queda
> desactivado. Para el BITalino real usen `python compilar.py iniciar`.

Docker sirve para demostraciones y para tener un entorno igual en todos los computadores.

```bash
python compilar.py docker
```

o a mano:

```bash
docker build -t rsi-monitor .
docker run -d --name rsi-monitor -p 127.0.0.1:8000:8000 -v rsi-monitor-datos:/app/datos rsi-monitor
```

- `-p 127.0.0.1:8000:8000`: la app solo se puede abrir desde este computador.
- `-v rsi-monitor-datos:/app/datos`: los datos quedan en un volumen y no se pierden al
  borrar el contenedor.
- Para detenerla: `docker stop rsi-monitor`.

La imagen tiene dos etapas: Node compila la página y `python:3.10.11-slim` la sirve.

## Dónde quedan los datos

En la carpeta `datos/` (en Docker, en el volumen `rsi-monitor-datos`). Git no la guarda.

| Archivo | Qué tiene |
|---|---|
| `EMG_features_AAAA-MM-DD_HH-MM-SS.csv` | una medición con el BITalino. Mismas columnas que el original: `Time (s)`, `Mean RMS (ADC)`, `Median MDF (Hz)` |
| `EMG_simulated_features_…csv` | lo mismo, en simulación |
| `config.json` | los ajustes. Se crea desde `backend/config.ejemplo.json`. `null` = usar el valor del código original |
| `descansos.json` | plantillas, historial de descansos y tiempo de uso de cada día |
| `servidor.log`, `servidor.pid` | salida y número de proceso de la app iniciada con `compilar.py` |

## API REST y mensajes del WebSocket

El backend escucha solo en `127.0.0.1`. Los `POST`/`PUT`/`DELETE` y el WebSocket revisan
el encabezado `Origin`, para que otra página web no pueda usar la app. Los errores
responden `{"detail": "mensaje en palabras simples"}` (400 dato inválido, 404 no existe,
409 no se puede ahora). Los modelos están en `backend/app/mensajes.py` y su copia para el
frontend en `frontend/lib/tipos.ts`.

### Rutas REST

| Método y ruta | Cuerpo | Qué hace |
|---|---|---|
| `GET /api/estado` | | foto completa (igual al mensaje `estado`) |
| `POST /api/medicion/encender` | `{modo: "real"\|"simulacion", escenario?, velocidad?, umbrales_sim?}` | enciende la medición |
| `POST /api/medicion/apagar` | | la apaga (cierra el último intervalo y llama a `stop()`) |
| `GET /api/puertos` | | `{detectados, todos}`: puertos serie |
| `POST /api/conexion/reconectar` | `{puerto: "COM5" \| null}` | conecta a ese puerto, o busca solo si es `null` |
| `GET /api/config` | | parámetros (valor, original, SIM_*, límites), duración del descanso, velocidades |
| `PUT /api/config` | `{parametros?: {NOMBRE: número\|null}, duracion_fatiga_min?, usar_umbrales_sim?, restaurar?}` | guarda ajustes |
| `POST /api/alerta/aceptar` | | acepta la alerta y empieza el descanso |
| `POST /api/descanso/iniciar` | `{plantilla: índice}` o `{minutos}` | descanso manual |
| `POST /api/descanso/terminar` | | "Terminar antes" |
| `GET /api/descansos/historial` | | historial (más reciente primero), minutos y cantidad de hoy |
| `GET/POST /api/plantillas` | `{nombre, duracion_min}` | listar / crear plantillas |
| `PUT/DELETE /api/plantillas/{índice}` | `{nombre, duracion_min}` | editar / borrar |

Las acciones que cambian el estado devuelven la foto completa.

### Mensajes del WebSocket (`/ws`)

Todos son JSON con un campo `tipo`. Al conectarse, el navegador recibe primero un
mensaje `estado` (la foto completa), así que al recargar la página no se pierde nada.
Los números que faltan (NaN en el original) llegan como `null`.

| `tipo` | Cuándo | Campos |
|---|---|---|
| `estado` | al conectarse, al encender/apagar y al guardar ajustes | `estado_app`, `medicion`, `conexion`, `parametros`, `calibracion`, `tendencia` (lista de puntos), `ultimo_bloque`, `alerta`, `descanso`, `reloj` |
| `conexion` | cambia la conexión o el estado de la medición | `estado_app`, `medicion`, `conexion` |
| `bloque` | una vez por bloque de N muestras | `bloque`: `n_medicion`, `ultimo_valor_emg`, `ultimo_rms`, `ultimo_mdf`, `muestras_recientes` (8), `texto_panel` |
| `tendencia` | un punto nuevo por intervalo | `estado_app`, `punto` (`tiempo`, `rms`, `mdf`), `calibracion` |
| `alerta` | sale o se acepta la alerta | `estado_app`, `alerta`: `pendiente`, `texto`, `aclaracion`, `minutos` |
| `descanso` | empieza o termina un descanso | `estado_app`, `evento` (`iniciado`/`terminado`), `completado`, `descanso` |
| `reloj` | cada segundo | `reloj` (`segundos_hoy`, `segundos_sesion`, `texto_hoy`, `texto_sesion`, `corriendo`), `segundos_restantes_descanso` |

Partes que se repiten:

- `medicion`: `encendida`, `modo_preferido`, `modo`, `escenario`, `velocidad`, `umbrales_sim`, `estado`, `ruta_csv`.
- `conexion`: `estado` (Desconectado / Buscando / Conectando / Conectado / Error), `puerto`, `version`, `detalle`, `en_docker`.
- `calibracion`: `calibrando`, `texto`, `linea_base` (`rms`, `mdf`, `texto`) o `null`.
- `descanso`: `activo`, `nombre`, `origen` (`fatiga`/`manual`), `duracion_planeada_s`, `segundos_restantes`, `minutos_hoy`, `cantidad_hoy`.

## Pruebas

```bash
python compilar.py probar
```

No necesitan el BITalino. Revisan, entre otras cosas, que la app dé los mismos resultados
que el código original, que `fatigue_test` alerte y `normal` no, el flujo alerta →
Aceptar → descanso → rearme, el reloj de uso, las plantillas, la API, el WebSocket y la
conexión con un BITalino falso. El detalle está en la documentación técnica.

## Problemas comunes

**La página dice "Sin conexión con el backend".** La app no está corriendo:
`python compilar.py iniciar`. Si sigue, revisen `datos/servidor.log`.

**La página dice que falta compilar el frontend.** `python compilar.py compilar`.

**No encuentra el BITalino.** Revisen que esté encendido y emparejado, y elijan el puerto
a mano en **Conexión**. El mensaje bajo el estado dice qué pasó con cada puerto.

**No salen notificaciones.** Aprieten **Activar notificaciones**. Si las bloquearon, la
página explica cómo permitirlas. Revisen también los permisos de notificaciones del
navegador en macOS o Windows. La ventana de alerta aparece igual.

**El puerto 8000 está ocupado.** Cambien `PUERTO` arriba de `compilar.py`.

## Falta probar

La app se programó y probó en Linux, con la simulación y con un BITalino falso. Todavía
no se probó con el BITalino real, ni en Windows ni en macOS. Antes de entregar, en cada
sistema:

1. `python compilar.py` termina sin errores.
2. Simulación ×10 con umbrales de prueba: alerta → Aceptar → cuenta regresiva →
   Terminar antes → vuelve a alertar. Recargar la página con la alerta abierta.
3. Con el BITalino: Detectar automáticamente, Encender, ver la calibración y los gráficos.
   Apagar el BITalino a mitad de la medición y ver que la app se reconecta al encenderlo.
4. Las notificaciones aparecen.
5. `python compilar.py docker` muestra el aviso de que el modo real no está disponible.

La app de escritorio anterior (PySide6) sigue en la rama `main`.
