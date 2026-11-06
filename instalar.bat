@echo off
rem Instalador de RSI Monitor para Windows: hagan doble clic en este archivo.
rem
rem 1. Busca Python 3.10 de 64 bits. Si no esta, lo instala con winget (el instalador
rem    de programas de Microsoft que viene con Windows), solo para este usuario.
rem 2. Crea el entorno .venv e instala las dependencias de requirements.txt.
rem 3. Crea los accesos directos "RSI Monitor" en el Escritorio y en el menu Inicio
rem    (herramientas\crear_accesos_directos.py).
rem 4. Abre la app. Con "instalar.bat /sinabrir" no la abre.
rem Se puede volver a ejecutar: completa lo que falte y no duplica nada.
rem
rem No descarga ni ejecuta nada por su cuenta: Python lo instala winget y las
rem dependencias, pip. Asi el antivirus no lo confunde con un virus.
rem Va sin tildes y con fin de linea CRLF, para que cmd lo lea bien.

setlocal
title Instalando RSI Monitor
cd /d "%~dp0"
set "CODIGO_VERSION=import sys, struct; sys.exit(0 if sys.version_info[:2] == (3, 10) and struct.calcsize('P') == 8 else 1)"
set "PYTHON_VENV=%~dp0.venv\Scripts\python.exe"

if not exist "app.py" (
    echo No se encontro app.py. Abran instalar.bat dentro de la carpeta RSI_Monitor,
    echo despues de descomprimir el ZIP.
    goto error
)

echo.
echo == Paso 1 de 4: Python 3.10
call :buscar_python
if defined PYTHON goto python_listo
where winget >nul 2>nul
if errorlevel 1 goto sin_python
echo Instalando Python 3.10 con winget. Puede tardar unos minutos...
winget install --id Python.Python.3.10 --exact --scope user --silent --accept-package-agreements --accept-source-agreements
call :buscar_python
if defined PYTHON goto python_listo

:sin_python
echo No se pudo instalar Python solo.
echo Instalen Python 3.10.11 de 64 bits desde la pagina que se va a abrir
echo y despues vuelvan a abrir instalar.bat.
start "" "https://www.python.org/downloads/release/python-31011/"
goto error

:python_listo
echo Python: %PYTHON%

echo.
echo == Paso 2 de 4: entorno y dependencias
if not exist "%PYTHON_VENV%" goto crear_venv
"%PYTHON_VENV%" -c "%CODIGO_VERSION%" >nul 2>nul
if not errorlevel 1 goto venv_listo
echo El entorno .venv no usa Python 3.10. Se vuelve a crear.
rmdir /s /q ".venv"
:crear_venv
"%PYTHON%" -m venv .venv
if errorlevel 1 goto error
:venv_listo
"%PYTHON_VENV%" -m pip install --upgrade pip --disable-pip-version-check
if errorlevel 1 goto error
"%PYTHON_VENV%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto error_pip
"%PYTHON_VENV%" -c "import PySide6, pyqtgraph, numpy, scipy, serial, bitalino"
if errorlevel 1 goto error
echo Dependencias listas.

echo.
echo == Paso 3 de 4: accesos directos
"%PYTHON_VENV%" herramientas\crear_accesos_directos.py
if errorlevel 1 echo No se pudieron crear. La app se puede abrir igual con instalar.bat.

echo.
echo == Paso 4 de 4: listo
echo RSI Monitor quedo instalado. Para abrirlo, usen el acceso directo "RSI Monitor".
if /i "%~1"=="/sinabrir" exit /b 0
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
echo Abriendo la app...
timeout /t 3 >nul
exit /b 0

rem Deja en PYTHON la ruta de un Python 3.10 de 64 bits, o la deja vacia.
:buscar_python
set "PYTHON="
for /f "usebackq delims=" %%P in (`py -3.10-64 -c "import sys; print(sys.executable)" 2^>nul`) do call :probar_python "%%P"
call :probar_python "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
call :probar_python "%ProgramFiles%\Python310\python.exe"
exit /b 0

:probar_python
if defined PYTHON exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "%CODIGO_VERSION%" >nul 2>nul
if not errorlevel 1 set "PYTHON=%~1"
exit /b 0

:error_pip
echo Si el error habla de rutas demasiado largas, muevan la carpeta a C:\RSI_Monitor.
:error
echo.
echo La instalacion no termino. Revisen el mensaje de arriba y la conexion a internet,
echo y vuelvan a abrir instalar.bat.
pause
exit /b 1
