# RSI Monitor — Grupo 2

RSI Monitor avisa cuando un músculo muestra señales de fatiga mientras trabajan en el
computador. Usa un BITalino con electrodos que mide sEMG por Bluetooth. Cuando detecta
una tendencia compatible con fatiga, abre un pop-up que sugiere tomar un descanso.

> La alerta es una ayuda. **No es un diagnóstico médico**, y el índice de fatiga del
> notebook todavía no está validado.

Es una aplicación de escritorio: Python mide y procesa la señal, y la ventana está
hecha con HTML, JavaScript y CSS (pywebview), igual que el proyecto *BitalinoPywebview*.
El procesamiento es el del notebook del grupo, `originales/bitalino_codigo (Ver 4.2).ipynb`.

## Empezar

Necesitan **Python 3.10.11** ([python.org](https://www.python.org/downloads/release/python-31011/);
en macOS también sirve `pyenv install 3.10.11`). Nada más.

```bash
git clone -b escritorio https://github.com/happymillipede/RSI_Monitor.git
cd RSI_Monitor
python iniciar.py --simular
```

La primera vez, `iniciar.py` crea el entorno `.venv` e instala lo necesario (necesita
Internet). Las veces siguientes solo abre la app. En Windows, si `python` no es la 3.10,
usen `py -3.10 iniciar.py`.

En Windows la ventana usa **Microsoft Edge WebView2**, que ya viene en Windows 10 y 11.
Si no está, se instala desde [Microsoft](https://developer.microsoft.com/microsoft-edge/webview2/).

## Cómo se usa

La pantalla principal sigue el diseño de Mateo y Ari:

1. **Conectar dispositivo**: elijan el puerto del BITalino (o **Detectar
   automáticamente**), o **Simulación** para probar sin BITalino. Arriba se ve el estado:
   Desconectado, Conectando, Conectado o Error.
2. **Calibrar**: mantengan el músculo en **reposo 15 s**. La app revisa la señal (que no
   esté saturada, el ruido de la red eléctrica y que el reposo sea estable) y calcula el
   umbral para saber cuándo el músculo está activo. Si sale **PASS**, todo bien. Si sale
   con avisos, el índice de fatiga queda suprimido: conviene revisar los electrodos y
   volver a calibrar.
3. **Comenzar**: graba hasta que aprieten **Detener**. No tiene duración fija (por
   seguridad se corta sola a las 24 h).
4. Mientras graba se ven la **Tendencia RMS**, la **Tendencia porcentual de fatiga**
   (0–100 %), el **Tiempo** de grabación y el muñeco, que se cansa junto con el músculo.
5. **Porcentaje de alerta** (60 % por defecto, el valor del notebook): cuando el índice
   pasa este porcentaje, y además el RMS subió y la MDF bajó lo suficiente y con una
   tendencia clara, se abre el pop-up **ALERTA — se sugiere tomar un descanso**. El pop-up
   queda encima de todas las demás ventanas. Se cierra con **Aceptar** o con la X.
6. Después de cerrar el pop-up, la alerta vuelve a estar disponible a los **10 minutos**
   de grabación (para no repetirse cada 5 s mientras dure la fatiga).

La pestaña **Detalles** muestra lo mismo que el notebook: la señal cruda, el RMS y la MDF
de cada bloque, la tendencia de MDF, el panel de adquisición, el resultado completo de la
calibración, los mensajes, los archivos y la **calibración de MVC** opcional.

### Simulación

En **Conectar dispositivo → Simulación** se elige el modo del simulador del notebook
(`normal`, `fatiga` o `contracción`) y la velocidad (×1 = tiempo real, ×5, ×10). Los
primeros 15 s de cada medición simulan reposo, para poder calibrar. Con el modo
`fatiga` a ×10, la alerta sale a los ~30 s (son ~317 s de señal simulada).

## Dónde quedan los datos

En la carpeta `datos/` (junto a `app.py`, o junto al `.exe`; en la `.app` de macOS, en
`Documentos/RSI_Monitor`). La pestaña Detalles tiene un botón para abrirla. Cada
grabación crea tres CSV, con los mismos nombres y columnas que el notebook:

| Archivo | Qué tiene |
|---|---|
| `EMG_TestNN_crudo.csv` | la señal cruda, una fila por muestra (≈ 90 MB por hora) |
| `EMG_TestNN_bloques.csv` | RMS, MDF, actividad, índice de fatiga y calidad de cada bloque de 1 s |
| `EMG_TestNN.csv` | tendencias cada 5 s: RMS, MDF, índice, segundos activos, calidad |

`NN` es el siguiente número libre (Test01, Test02…). `ajustes.json` guarda el porcentaje
de alerta, el último puerto que funcionó y la simulación elegida.

## Crear el programa (sin Python)

```bash
python generar_exe.py
```

En Windows crea `dist\RSI_Monitor.exe`; en macOS, `dist/RSI_Monitor.app`. Hay que
ejecutarlo en cada sistema. El programa resultante se puede copiar a otro computador
sin instalar Python.

## Pruebas

```bash
.venv/bin/python -m pytest -q          # Windows: .venv\Scripts\python -m pytest -q
```

Las pruebas no necesitan el BITalino. La más importante corre **el código del notebook
4.2 tal cual** y el de la app con la misma señal simulada, y comprueba que los tres CSV
sean **idénticos byte a byte**, igual que la calibración, la MVC y la alerta.

## Problemas comunes

**No encuentra el BITalino.** Revisen que esté encendido y emparejado por Bluetooth en
la configuración del computador (la clave suele ser `1234`). En macOS el puerto se llama
`/dev/tty.BITalino-…`; en Windows es un `COM` de Bluetooth (en Configuración →
Bluetooth → Más opciones → Puertos COM, el «Saliente»).

**Comenzar está desactivado.** Primero hay que conectar y calibrar.

**El índice de fatiga no aparece.** Durante los primeros segundos se juntan 10 s de
bloques activos para la línea base. Si la calibración no fue PASS, el índice queda
suprimido; vuelvan a calibrar.

**En Linux no abre la ventana.** pywebview necesita Qt: `pip install "pywebview[qt]"`
(`iniciar.py` ya lo hace).

## Falta probar

La app se programó en Linux y se probó con el simulador y con un BITalino imitado. No se
ha probado con el BITalino real, ni el `.exe` en Windows, ni la `.app` en macOS.

Más detalles para quien quiera cambiar el código: [DOCUMENTACION_TECNICA.md](DOCUMENTACION_TECNICA.md).
Las versiones anteriores de la app están en las ramas `main` (escritorio con PySide6) y
`web` (FastAPI + Next.js).
