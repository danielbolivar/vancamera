# Guía de Instalación - VanCamera

## Instalación del Driver OBS-VirtualCam

VanCamera requiere el driver **OBS-VirtualCam Standalone (Legacy v2.0.5)** para funcionar como cámara virtual en Windows.

### Paso 1: Descargar OBS-VirtualCam

1. Visita el repositorio oficial: https://github.com/Fenrirthviti/obs-virtual-cam/releases
2. Descarga la versión **Legacy v2.0.5** (OBS-VirtualCam-v2.0.5.exe)
3. **Importante**: No instales OBS Studio completo, solo necesitas el driver standalone

### Paso 2: Instalar el Driver

1. Ejecuta `OBS-VirtualCam-v2.0.5.exe` como Administrador (clic derecho → Ejecutar como administrador)
2. Sigue el asistente de instalación
3. Acepta la instalación del certificado digital si Windows lo solicita
4. Reinicia tu PC si es necesario

### Paso 3: Verificar Instalación

1. Abre la aplicación de Configuración de Windows
2. Ve a "Privacidad" → "Cámara"
3. Deberías ver "OBS-Camera" en la lista de dispositivos de cámara disponibles

O verifica desde PowerShell:
```powershell
Get-PnpDevice | Where-Object {$_.FriendlyName -like "*OBS*"}
```

### Paso 4: Configurar Discord/Zoom/Teams

1. Abre Discord (o tu aplicación de videollamada)
2. Ve a Configuración → Video
3. Selecciona "OBS-Camera" como dispositivo de cámara
4. Deberías ver el video de VanCamera

## Instalación de ADB (para modo USB)

### Opción 1: Android SDK Platform Tools (Recomendado)

1. Descarga Android SDK Platform Tools desde: https://developer.android.com/studio/releases/platform-tools
2. Extrae el archivo ZIP
3. Agrega la carpeta `platform-tools` a tu PATH de Windows:
   - Busca "Variables de entorno" en Windows
   - Edita la variable PATH
   - Agrega la ruta completa a `platform-tools` (ej: `C:\platform-tools`)

### Opción 2: Usar Android Studio

Si ya tienes Android Studio instalado:
1. ADB está incluido en `%LOCALAPPDATA%\Android\Sdk\platform-tools`
2. Agrega esta ruta a tu PATH

### Verificar Instalación de ADB

Abre PowerShell y ejecuta:
```powershell
adb version
```

Deberías ver la versión de ADB instalada.

## Instalación de Python

1. Descarga Python 3.8 o superior desde: https://www.python.org/downloads/
2. Durante la instalación, marca la opción "Add Python to PATH"
3. Verifica la instalación:
   ```powershell
   python --version
   ```

## Instalación de Dependencias Python

1. Abre PowerShell en el directorio `windows/`
2. Ejecuta:
   ```powershell
   pip install -r requirements.txt
   ```

Si encuentras problemas con `av` (PyAV), puedes instalarlo desde:
```powershell
pip install av --no-binary av
```

## Habilitar Depuración USB en Android

1. Ve a Configuración → Acerca del teléfono
2. Toca 7 veces en "Número de compilación" para activar Opciones de desarrollador
3. Ve a Configuración → Opciones de desarrollador
4. Activa "Depuración USB"
5. Conecta tu dispositivo vía USB
6. Acepta el diálogo de autorización en tu Android

## Verificar Conexión ADB

Con tu Android conectado vía USB, ejecuta:
```powershell
adb devices
```

Deberías ver tu dispositivo listado. Si aparece "unauthorized", acepta el diálogo en tu Android.

## Próximos Pasos

Una vez completada la instalación, consulta el [README.md](README.md) para comenzar a usar VanCamera.
