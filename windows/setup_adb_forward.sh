#!/bin/bash
# Script bash para configurar ADB port forwarding (para WSL o Linux)
# Conecta el puerto del servidor Windows con el puerto del dispositivo Android

LOCAL_PORT=${1:-443}
REMOTE_PORT=${2:-443}

echo "=== VanCamera ADB Port Forwarding Setup ==="
echo ""

# Verificar que ADB esté disponible
if ! command -v adb &> /dev/null; then
    echo "ERROR: ADB no está instalado o no está en el PATH"
    echo ""
    echo "Por favor instala Android SDK Platform Tools:"
    echo "https://developer.android.com/studio/releases/platform-tools"
    exit 1
fi

echo "ADB encontrado:"
adb version
echo ""

# Verificar que haya un dispositivo conectado
echo "Verificando dispositivos conectados..."
DEVICES=$(adb devices | grep "device$")

if [ -z "$DEVICES" ]; then
    echo "ERROR: No se encontraron dispositivos Android conectados"
    echo ""
    echo "Por favor:"
    echo "1. Conecta tu dispositivo Android vía USB"
    echo "2. Habilita 'Depuración USB' en Opciones de desarrollador"
    echo "3. Acepta el diálogo de autorización en tu dispositivo"
    echo ""
    echo "Dispositivos detectados:"
    adb devices
    exit 1
fi

echo "Dispositivo(s) encontrado(s):"
echo "$DEVICES"
echo ""

# Verificar si ya existe un forward para este puerto
echo "Verificando port forwards existentes..."
EXISTING_FORWARD=$(adb forward --list | grep "tcp:$LOCAL_PORT")

if [ ! -z "$EXISTING_FORWARD" ]; then
    echo "ADVERTENCIA: Ya existe un port forward para el puerto $LOCAL_PORT"
    echo "$EXISTING_FORWARD"
    echo ""
    read -p "¿Deseas eliminarlo y crear uno nuevo? (S/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        echo "Eliminando port forward existente..."
        adb forward --remove tcp:$LOCAL_PORT
    else
        echo "Manteniendo port forward existente."
        echo ""
        echo "Para usar VanCamera:"
        echo "1. En la app Android, configura IP: 127.0.0.1 y Puerto: $LOCAL_PORT"
        echo "2. En la app Windows, configura IP: 127.0.0.1 y Puerto: $LOCAL_PORT"
        exit 0
    fi
fi

# Crear nuevo port forward
echo "Creando port forward: tcp:$LOCAL_PORT -> tcp:$REMOTE_PORT"
if adb forward tcp:$LOCAL_PORT tcp:$REMOTE_PORT; then
    echo "Port forward creado exitosamente!"
    echo ""
    echo "=== Configuración para VanCamera ==="
    echo ""
    echo "En la app Android:"
    echo "  - IP del servidor: 127.0.0.1"
    echo "  - Puerto: $LOCAL_PORT"
    echo "  - Modo: USB"
    echo ""
    echo "En la app Windows:"
    echo "  - IP del servidor: 127.0.0.1"
    echo "  - Puerto: $LOCAL_PORT"
    echo "  - Modo: USB"
    echo ""
    echo "Para verificar el port forward:"
    echo "  adb forward --list"
    echo ""
    echo "Para eliminar el port forward:"
    echo "  adb forward --remove tcp:$LOCAL_PORT"
else
    echo "ERROR al crear port forward"
    exit 1
fi
