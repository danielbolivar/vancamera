# Script PowerShell para configurar ADB port forwarding
# Conecta el puerto del servidor Windows con el puerto del dispositivo Android

param(
    [int]$LocalPort = 8443,
    [int]$RemotePort = 8443
)

Write-Host "=== VanCamera ADB Port Forwarding Setup ===" -ForegroundColor Cyan
Write-Host ""

# Verificar que ADB esté disponible
try {
    $adbVersion = adb version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "ADB no encontrado"
    }
    Write-Host "ADB encontrado:" -ForegroundColor Green
    Write-Host $adbVersion[0]
    Write-Host ""
} catch {
    Write-Host "ERROR: ADB no está instalado o no está en el PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "Por favor instala Android SDK Platform Tools:" -ForegroundColor Yellow
    Write-Host "https://developer.android.com/studio/releases/platform-tools" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "O agrega ADB a tu PATH si ya está instalado." -ForegroundColor Yellow
    exit 1
}

# Verificar que haya un dispositivo conectado
Write-Host "Verificando dispositivos conectados..." -ForegroundColor Cyan
$devices = adb devices 2>&1
$deviceLines = $devices | Select-String -Pattern "device$"

if ($deviceLines.Count -eq 0) {
    Write-Host "ERROR: No se encontraron dispositivos Android conectados" -ForegroundColor Red
    Write-Host ""
    Write-Host "Por favor:" -ForegroundColor Yellow
    Write-Host "1. Conecta tu dispositivo Android vía USB" -ForegroundColor Yellow
    Write-Host "2. Habilita 'Depuración USB' en Opciones de desarrollador" -ForegroundColor Yellow
    Write-Host "3. Acepta el diálogo de autorización en tu dispositivo" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Dispositivos detectados:" -ForegroundColor Yellow
    Write-Host $devices
    exit 1
}

Write-Host "Dispositivo(s) encontrado(s):" -ForegroundColor Green
$deviceLines | ForEach-Object { Write-Host "  $_" }
Write-Host ""

# Verificar si ya existe un forward para este puerto
Write-Host "Verificando port forwards existentes..." -ForegroundColor Cyan
$existingForwards = adb forward --list 2>&1
$portForward = $existingForwards | Select-String -Pattern "tcp:$LocalPort"

if ($portForward) {
    Write-Host "ADVERTENCIA: Ya existe un port forward para el puerto $LocalPort" -ForegroundColor Yellow
    Write-Host $portForward
    Write-Host ""
    $response = Read-Host "¿Deseas eliminarlo y crear uno nuevo? (S/N)"
    if ($response -eq "S" -or $response -eq "s") {
        Write-Host "Eliminando port forward existente..." -ForegroundColor Cyan
        adb forward --remove tcp:$LocalPort 2>&1 | Out-Null
    } else {
        Write-Host "Manteniendo port forward existente." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Para usar VanCamera:" -ForegroundColor Cyan
        Write-Host "1. En la app Android, configura IP: 127.0.0.1 y Puerto: $LocalPort" -ForegroundColor White
        Write-Host "2. En la app Windows, configura IP: 127.0.0.1 y Puerto: $LocalPort" -ForegroundColor White
        exit 0
    }
}

# Crear nuevo port forward
Write-Host "Creando port forward: tcp:$LocalPort -> tcp:$RemotePort" -ForegroundColor Cyan
$forwardResult = adb forward tcp:$LocalPort tcp:$RemotePort 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "Port forward creado exitosamente!" -ForegroundColor Green
    Write-Host ""
    Write-Host "=== Configuración para VanCamera ===" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "En la app Android:" -ForegroundColor Yellow
    Write-Host "  - IP del servidor: 127.0.0.1" -ForegroundColor White
    Write-Host "  - Puerto: $LocalPort" -ForegroundColor White
    Write-Host "  - Modo: USB" -ForegroundColor White
    Write-Host ""
    Write-Host "En la app Windows:" -ForegroundColor Yellow
    Write-Host "  - IP del servidor: 127.0.0.1" -ForegroundColor White
    Write-Host "  - Puerto: $LocalPort" -ForegroundColor White
    Write-Host "  - Modo: USB" -ForegroundColor White
    Write-Host ""
    Write-Host "Para verificar el port forward:" -ForegroundColor Cyan
    Write-Host "  adb forward --list" -ForegroundColor White
    Write-Host ""
    Write-Host "Para eliminar el port forward:" -ForegroundColor Cyan
    Write-Host "  adb forward --remove tcp:$LocalPort" -ForegroundColor White
} else {
    Write-Host "ERROR al crear port forward:" -ForegroundColor Red
    Write-Host $forwardResult
    exit 1
}
