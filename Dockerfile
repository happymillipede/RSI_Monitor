# Imagen Docker de RSI Monitor (solo modo simulación).
#
# Docker Desktop en Windows y macOS corre dentro de una máquina virtual y no puede
# usar los puertos COM ni los /dev/tty.* del Bluetooth. Por eso aquí solo funciona la
# simulación: para el BITalino real, usen "python compilar.py iniciar".
#
# Etapa 1 (Node): compila el frontend (exportación estática).
# Etapa 2 (Python 3.10.11): instala el backend y sirve todo en un solo puerto.
#
# Crear y usar (o simplemente: python compilar.py docker):
#   docker build -t rsi-monitor .
#   docker run -d --name rsi-monitor -p 127.0.0.1:8000:8000 -v rsi-monitor-datos:/app/datos rsi-monitor
#
# Qué se puede editar aquí: las versiones de las imágenes base.

# --- Etapa 1: frontend ---
FROM node:24.21.0-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Etapa 2: backend ---
FROM python:3.10.11-slim
# RSI_EN_DOCKER=1: la interfaz avisa que el modo real no está disponible.
ENV RSI_EN_DOCKER=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

# El paquete bitalino pide PyBluez, que no se puede instalar en esta imagen y solo sirve
# para conectarse por dirección MAC. Como aquí solo hay simulación, se instala sin él.
COPY backend/requirements.txt backend/
RUN grep -v "^bitalino" backend/requirements.txt > /tmp/requisitos.txt \
    && pip install --no-cache-dir -r /tmp/requisitos.txt \
    && grep "^bitalino" backend/requirements.txt | xargs pip install --no-cache-dir --no-deps

COPY ["Código_Bitalino_Python.py", "./"]
COPY backend/ backend/
COPY --from=frontend /app/frontend/out backend/estaticos

# datos/: config.json, descansos.json y los CSV (montar un volumen para no perderlos)
VOLUME /app/datos
EXPOSE 8000
WORKDIR /app/backend
# 0.0.0.0 dentro del contenedor; publiquen el puerto solo en 127.0.0.1 (ver arriba).
CMD ["python", "-m", "app.main", "--host", "0.0.0.0", "--sim"]
