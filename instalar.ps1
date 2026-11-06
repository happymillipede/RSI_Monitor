# Instalador de RSI Monitor para Windows.
#
# Se abre con doble clic en instalar.bat. La primera vez hace todo lo necesario:
#   1. busca Python 3.10 (64 bits). Si no está, descarga el instalador oficial de
#      python.org, revisa que el archivo sea el original y lo instala solo para este
#      usuario, sin pedir permisos de administrador;
#   2. crea el entorno .venv e instala las dependencias de requirements.txt;
#   3. deja el inicio con el sistema como diga config.json (activado por defecto);
#   4. crea los accesos directos "RSI Monitor" en el Escritorio y en el menú Inicio;
#   5. abre la app.
# Se puede volver a ejecutar: completa lo que falte y no duplica nada.
# Lo que muestra en pantalla queda también en instalacion.log.
#
# Opciones (desde PowerShell):  .\instalar.bat -SinAbrir    instala y no abre la app
#
# Qué se puede editar aquí: las constantes del principio.

param([switch]$SinAbrir)

$ErrorActionPreference = 'Stop'
# Sin esto, Invoke-WebRequest descarga muy lento en Windows PowerShell 5.
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$VERSION_PYTHON = '3.10.11'
$URL_PYTHON = "https://www.python.org/ftp/python/$VERSION_PYTHON/python-$VERSION_PYTHON-amd64.exe"
# SHA-256 de python-3.10.11-amd64.exe (su MD5 coincide con el publicado en python.org).
$SHA256_PYTHON = 'D8DEDE5005564B408BA50317108B765ED9C3C510342A598F9FD42681CBE0648B'
$CARPETA_PYTHON = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310'
$NOMBRE_ACCESO = 'RSI Monitor'

$carpeta = $PSScriptRoot
$carpetaVenv = Join-Path $carpeta '.venv'
$pythonVenv = Join-Path $carpetaVenv 'Scripts\python.exe'
$pythonwVenv = Join-Path $carpetaVenv 'Scripts\pythonw.exe'
$app = Join-Path $carpeta 'app.py'

# Termina bien solo si es Python 3.10 de 64 bits.
$CODIGO_VERSION = "import sys, struct; sys.exit(0 if sys.version_info[:2] == (3, 10) and struct.calcsize('P') == 8 else 1)"
# Deja el inicio con el sistema como diga config.json, con el mismo código que usa la app.
$CODIGO_AUTOINICIO = "from nucleo import rutas; from nucleo.configuracion import Configuracion; from sistema import autoinicio; activar = Configuracion(rutas.carpeta_base())['sistema']['iniciar_con_el_sistema']; autoinicio.aplicar(activar); print('activado' if activar else 'desactivado')"

function Escribir-Paso([string]$texto) {
    Write-Host ''
    Write-Host "== $texto" -ForegroundColor Cyan
}

# Ejecuta un programa, muestra lo que escribe y falla si termina con error.
function Ejecutar([string]$programa, [string[]]$argumentos) {
    $anterior = $ErrorActionPreference
    # En PowerShell 5, con 'Stop', cualquier aviso de pip en stderr cortaría el script.
    $ErrorActionPreference = 'Continue'
    try {
        & $programa @argumentos 2>&1 | ForEach-Object { "$_" } | Out-Host
        $codigo = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $anterior
    }
    if ($codigo -ne 0) {
        throw "Falló (código $codigo): $programa $($argumentos -join ' ')"
    }
}

function Es-Python310([string]$python) {
    if (-not $python -or -not (Test-Path -LiteralPath $python)) { return $false }
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $python -c $CODIGO_VERSION 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $anterior
    }
}

# La ruta de un Python 3.10 de 64 bits ya instalado, o $null.
function Buscar-Python {
    $candidatos = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $anterior = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $ruta = & py -3.10-64 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $ruta) { $candidatos += "$ruta".Trim() }
        } catch {
        } finally {
            $ErrorActionPreference = $anterior
        }
    }
    # El python.exe de WindowsApps no es Python: abre la Microsoft Store.
    $enRuta = Get-Command python -All -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*\WindowsApps\*' }
    foreach ($comando in @($enRuta)) { if ($comando) { $candidatos += $comando.Source } }
    $candidatos += (Join-Path $CARPETA_PYTHON 'python.exe')
    $candidatos += (Join-Path $env:ProgramFiles 'Python310\python.exe')
    foreach ($candidato in $candidatos) {
        if (Es-Python310 $candidato) { return $candidato }
    }
    return $null
}

function Instalar-Python {
    $instalador = Join-Path $env:TEMP "python-$VERSION_PYTHON-amd64.exe"
    Write-Host "Descargando Python $VERSION_PYTHON desde python.org (unos 28 MB)..."
    Invoke-WebRequest -Uri $URL_PYTHON -OutFile $instalador -UseBasicParsing
    $hash = (Get-FileHash -LiteralPath $instalador -Algorithm SHA256).Hash
    if ($hash -ne $SHA256_PYTHON) {
        Remove-Item -LiteralPath $instalador -Force
        throw 'El instalador de Python descargado no es el original (no coincide su SHA-256). Prueben de nuevo más tarde.'
    }
    Write-Host 'Instalando Python solo para este usuario (puede tardar un par de minutos)...'
    $opciones = @(
        '/quiet',
        'InstallAllUsers=0',
        "TargetDir=`"$CARPETA_PYTHON`"",
        'Include_launcher=1',
        'InstallLauncherAllUsers=0',
        'PrependPath=0',
        'AssociateFiles=0',
        'Shortcuts=0',
        'Include_test=0',
        'Include_doc=0'
    )
    $proceso = Start-Process -FilePath $instalador -ArgumentList $opciones -Wait -PassThru
    Remove-Item -LiteralPath $instalador -Force -ErrorAction SilentlyContinue
    # 3010 = instalado, pide reiniciar (no hace falta para usarlo).
    if ($proceso.ExitCode -ne 0 -and $proceso.ExitCode -ne 3010) {
        throw "El instalador de Python terminó con el código $($proceso.ExitCode)."
    }
}

function Crear-Acceso([string]$carpetaDestino) {
    if (-not $carpetaDestino -or -not (Test-Path -LiteralPath $carpetaDestino)) { return }
    $ruta = Join-Path $carpetaDestino "$NOMBRE_ACCESO.lnk"
    $acceso = (New-Object -ComObject WScript.Shell).CreateShortcut($ruta)
    $acceso.TargetPath = $pythonwVenv
    $acceso.Arguments = "`"$app`""
    $acceso.WorkingDirectory = $carpeta
    $acceso.IconLocation = (Join-Path $carpeta 'recursos\icono.ico') + ',0'
    $acceso.Description = 'Detector de fatiga muscular con BITalino'
    $acceso.Save()
    Write-Host "Acceso directo: $ruta"
}

try {
    Start-Transcript -LiteralPath (Join-Path $carpeta 'instalacion.log') | Out-Null
} catch {
    # Sin el registro igual se puede instalar.
}

try {
    Write-Host "Instalando RSI Monitor en $carpeta"
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'RSI Monitor necesita Windows de 64 bits.'
    }
    if (-not (Test-Path -LiteralPath $app)) {
        throw 'No se encontró app.py. Ejecuten instalar.bat desde la carpeta RSI_Monitor, después de descomprimirla.'
    }
    Set-Location -LiteralPath $carpeta

    Escribir-Paso 'Paso 1 de 5: Python 3.10'
    $python = Buscar-Python
    if ($python) {
        Write-Host "Ya está instalado: $python"
    } else {
        Instalar-Python
        $python = Buscar-Python
        if (-not $python) { throw 'Se instaló Python, pero no se encontró. Cierren esta ventana y vuelvan a abrir instalar.bat.' }
        Write-Host "Instalado: $python"
    }

    Escribir-Paso 'Paso 2 de 5: entorno y dependencias'
    if ((Test-Path -LiteralPath $carpetaVenv) -and -not (Es-Python310 $pythonVenv)) {
        Write-Host 'El entorno .venv existente no usa Python 3.10. Se vuelve a crear.'
        Remove-Item -LiteralPath $carpetaVenv -Recurse -Force
    }
    if (-not (Test-Path -LiteralPath $pythonVenv)) {
        Ejecutar $python @('-m', 'venv', $carpetaVenv)
    }
    Ejecutar $pythonVenv @('-m', 'pip', 'install', '--upgrade', 'pip', '--disable-pip-version-check')
    Ejecutar $pythonVenv @('-m', 'pip', 'install', '-r', (Join-Path $carpeta 'requirements.txt'), '--disable-pip-version-check')
    Ejecutar $pythonVenv @('-c', 'import PySide6, pyqtgraph, numpy, scipy, serial, bitalino')
    Write-Host 'Dependencias listas.'

    Escribir-Paso 'Paso 3 de 5: iniciar con el sistema'
    try {
        Ejecutar $pythonVenv @('-c', $CODIGO_AUTOINICIO)
    } catch {
        Write-Host "No se pudo configurar (se puede cambiar después en Ajustes): $_" -ForegroundColor Yellow
    }

    Escribir-Paso 'Paso 4 de 5: accesos directos'
    Crear-Acceso ([Environment]::GetFolderPath('Desktop'))
    Crear-Acceso ([Environment]::GetFolderPath('Programs'))

    Escribir-Paso 'Paso 5 de 5: listo'
    Write-Host 'RSI Monitor quedó instalado. Para abrirlo, usen el acceso directo "RSI Monitor".' -ForegroundColor Green
    if (-not $SinAbrir) {
        Start-Process -FilePath $pythonwVenv -ArgumentList "`"$app`"" -WorkingDirectory $carpeta
        Write-Host 'Abriendo la app...'
        Start-Sleep -Seconds 3
    }
    $codigoSalida = 0
} catch {
    Write-Host ''
    Write-Host "ERROR: $_" -ForegroundColor Red
    Write-Host 'Revisen la conexión a internet y vuelvan a abrir instalar.bat.'
    Write-Host 'Si el error habla de rutas demasiado largas, muevan la carpeta a C:\RSI_Monitor.'
    Write-Host 'El detalle quedó en instalacion.log.'
    $codigoSalida = 1
} finally {
    try { Stop-Transcript | Out-Null } catch { }
}
exit $codigoSalida
