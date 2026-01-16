# VanCamera

Sistema Open Source y seguro que permite usar la cámara de un celular Android como webcam de alta calidad y baja latencia para Windows, compatible nativamente con Discord, sin depender de software comercial pesado o con publicidad.

## Filosofía

"Do It Yourself" (Hazlo tú mismo), priorizando el control sobre los datos, la seguridad en redes públicas (como la de la universidad) y la eficiencia del código.

## Características

- **Alta Calidad**: Codificación H.264 por hardware en Android
- **Baja Latencia**: Protocolo TCP optimizado con TLS 1.3
- **Seguro**: Cifrado de grado militar para redes públicas
- **Flexible**: Soporte para conexión WiFi y USB (ADB)
- **Nativo**: Compatible con Discord, Zoom, Teams y cualquier aplicación que use DirectShow

## Arquitectura

El sistema consta de dos componentes:

1. **App Android (Kotlin)**: Captura video, codifica H.264, transmite vía TLS 1.3
2. **App Windows (Python)**: Recibe video, decodifica, muestra preview y alimenta OBS-VirtualCam

## Requisitos

### Android
- Android 7.0 (API 24) o superior
- Cámara frontal o trasera funcional
- Conexión WiFi o USB con ADB habilitado

### Windows
- Windows 10 o superior
- Python 3.8 o superior
- OBS-VirtualCam Standalone (Legacy v2.0.5) instalado
- ADB instalado (para modo USB)

## Instalación Rápida

### 1. Instalar OBS-VirtualCam

Consulta [INSTALL.md](INSTALL.md) para instrucciones detalladas de instalación del driver virtual camera.

### 2. Configurar App Android

1. Abre el proyecto en Android Studio
2. Sincroniza las dependencias Gradle
3. Compila e instala en tu dispositivo Android

### 3. Configurar App Windows

1. Navega al directorio `windows/`
2. Instala dependencias:
   ```powershell
   pip install -r requirements.txt
   ```
3. Ejecuta la aplicación:
   ```powershell
   python main.py
   ```

## Uso

### Modo WiFi

1. Asegúrate de que tu PC y Android estén en la misma red WiFi
2. En la app Android, configura la IP de tu PC y el puerto (por defecto 443)
3. Inicia la transmisión desde Android
4. En la app Windows, configura la misma IP y puerto, luego inicia la recepción

### Modo USB

1. Conecta tu Android a la PC vía USB
2. Habilita depuración USB en Android
3. Ejecuta el script de port forwarding:
   ```powershell
   .\windows\setup_adb_forward.ps1
   ```
4. En ambas apps, selecciona modo "USB"
5. Inicia la transmisión desde Android y la recepción desde Windows

## Configuración de Video

La app Android permite configurar:
- **Resolución**: 720p, 1080p (según disponibilidad del dispositivo)
- **FPS**: 30, 60 fps
- **Bitrate**: Ajustable según calidad deseada

Presets disponibles:
- 720p @ 30fps (recomendado para WiFi)
- 720p @ 60fps (más fluido)
- 1080p @ 30fps (máxima calidad)

## Seguridad

VanCamera usa TLS 1.3 para cifrar toda la comunicación. Los certificados se generan automáticamente en la primera ejecución y se comparten entre Android y Windows mediante QR code o archivo.

## Solución de Problemas

Consulta [TROUBLESHOOTING.md](TROUBLESHOOTING.md) para soluciones a problemas comunes.

## Contribuir

Este es un proyecto Open Source. Las contribuciones son bienvenidas.

## Licencia

[Especificar licencia]

## Créditos

- OBS-VirtualCam: Driver de cámara virtual
- CameraX: API de captura de video en Android
- MediaCodec: Codificación hardware H.264
