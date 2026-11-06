# RSI Monitor — Grupo 2

RSI Monitor avisa cuando un músculo muestra señales de fatiga mientras trabajan en el
computador. Usa un BITalino con 3 electrodos conectado por Bluetooth.
Cuando detecta fatiga, les pide que descansen unos minutos.

> La alerta es una ayuda. **No es un diagnóstico médico.**

> **Rama `web` (en construcción):** aquí la app de escritorio se está convirtiendo en una
> app web local (FastAPI + Next.js). Por ahora solo funciona el modo sin navegador:
> `cd backend && python -m app.main --sim --headless --velocidad 10`.
> La app de escritorio sigue en la rama `main`. El README completo llega en la fase 6.

## Empezar en 5 minutos (sin el BITalino)

Necesitan **Python 3.10.11**.

**En macOS** (con pyenv):

```bash
cd RSI_Monitor
pyenv install 3.10.11
pyenv local 3.10.11
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**En Windows** (PowerShell, con Python 3.10.11 de python.org):

```powershell
cd RSI_Monitor
py -3.10 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Después abran la app en modo simulación:

```bash
python app.py --sim --umbrales-sim
```

1. Elijan el escenario **fatigue_test** y la velocidad **×10**.
2. Aprieten **Encender**.
3. Primero dice "Calibrando línea base". Luego aparecen los gráficos.
4. A los pocos segundos sale la alerta "Riesgo de fatiga muscular, descanse 10 minutos".
5. Aprieten **Aceptar**. Empieza la cuenta regresiva del descanso.
6. Si aprietan **Terminar antes**, la app vuelve a vigilar la fatiga.

`--umbrales-sim` usa los umbrales de prueba del código original, que alertan rápido.
Sin esa opción, la simulación usa los umbrales normales y `fatigue_test` no alerta.

## Usar con el BITalino

1. Emparejen el BITalino por Bluetooth desde la configuración del computador. Se hace
   una sola vez. La clave suele ser `1234`.
2. Abran la app con `python app.py`.
3. En **Modo**, elijan **BITalino** y aprieten **Encender**.
4. La app busca el BITalino sola. Cuando lo encuentra, dice "Calibrando línea base".
5. Durante la calibración, mantengan la postura y el ritmo de trabajo normales.

Si el Bluetooth se corta, la app lo vuelve a buscar sola y sigue midiendo.

## Lo que hace la app

- **Encender / Apagar**: mide hasta que la apaguen.
- **Gráficos**: muestran cómo cambian la intensidad (RMS) y la frecuencia (MDF) del músculo.
- **Alerta de fatiga**: una ventana que queda encima de todo. Solo se cierra con **Aceptar**.
- **Descansos**: la cuenta regresiva empieza al aceptar la alerta. También pueden tomar
  un descanso cuando quieran, desde la pestaña **Descansos**.
- **Historial**: la pestaña **Descansos** muestra los descansos anteriores y el total de hoy.
- **Reloj de uso**: cuánto tiempo midieron hoy y en esta sesión.
- **Bandeja**: si cierran la ventana, la app sigue funcionando en la bandeja.
  En Windows está junto al reloj y en macOS en la barra de arriba.
- **Iniciar con el sistema**: la app se abre sola al encender el computador.

Para cerrar la app del todo, usen **Salir** en el menú del ícono o en el menú
**RSI Monitor**. La X de la ventana solo la esconde.

## Dónde quedan sus datos

Usen el menú **RSI Monitor → Abrir carpeta de datos**. Ahí están:

| Archivo | Qué tiene |
|---|---|
| `EMG_features_…csv` | Los datos de cada medición. Hay uno por sesión, con fecha y hora en el nombre |
| `descansos.json` | El historial de descansos |
| `uso_diario.json` | El tiempo medido cada día |

## Cambiar ajustes

Abran el menú **RSI Monitor → Ajustes**. Ahí pueden cambiar:

- los umbrales y tiempos de la detección (el botón **Restaurar** vuelve al valor del código original);
- los minutos de descanso;
- el puerto del BITalino, si la app no lo encuentra sola;
- si la app se abre al encender el computador.

Los ajustes se guardan en `config.json`.

## Crear el programa para instalar

Hay que hacerlo en cada sistema: el `.exe` en Windows y la `.app` en macOS.

**Windows:**

1. Abran PowerShell en la carpeta `RSI_Monitor`.
2. Activen el entorno: `.venv\Scripts\activate`
3. Ejecuten: `pyinstaller RSI_Monitor.spec`
4. El programa queda en `dist\RSI_Monitor.exe`. La primera vez demora unos segundos en abrir.

**macOS:**

1. Abran la Terminal en la carpeta `RSI_Monitor`.
2. Activen el entorno: `source .venv/bin/activate`
3. Ejecuten: `pyinstaller RSI_Monitor.spec`
4. La app queda en `dist/RSI_Monitor.app`. Muévanla a la carpeta **Aplicaciones**.

### Permisos en macOS

- La primera vez, macOS pide permiso para usar **Bluetooth** y para mostrar
  **notificaciones**. Acepten los dos.
- Como la app no está firmada, la primera vez ábranla con clic derecho → **Abrir**.

## Problemas comunes

**La app no encuentra el BITalino.**
Revisen que esté encendido y emparejado. Si sigue sin aparecer, elijan el puerto en
**Ajustes → Puerto**. En Windows, el puerto está en Configuración → Bluetooth →
Más opciones de Bluetooth → Puertos COM. Usen el que dice "Saliente".

**La app desapareció.**
Sigue funcionando en la bandeja. Hagan clic en su ícono y elijan **Mostrar**.

**No salen notificaciones.**
Revisen los permisos de notificaciones del sistema. La ventana de alerta aparece igual.

**macOS dice que la app "está dañada".**
Ejecuten en la Terminal:

```bash
xattr -dr com.apple.quarantine /Applications/RSI_Monitor.app
```

## Más información

Los detalles técnicos están en [DOCUMENTACION_TECNICA.md](DOCUMENTACION_TECNICA.md).
Ahí se explica cómo está organizado el código, cómo correr las pruebas, cómo se conecta
con el BITalino y qué observamos en el código original.
