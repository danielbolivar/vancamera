# Solución de Problemas - VanCamera

## Problemas Comunes

### La cámara virtual no aparece en Discord/Teams

**Síntomas**: OBS-Camera no aparece en la lista de cámaras disponibles.

**Soluciones**:
1. Verifica que OBS-VirtualCam esté instalado correctamente (ver [INSTALL.md](INSTALL.md))
2. Reinicia tu PC después de instalar el driver
3. Verifica que el driver esté habilitado:
   ```powershell
   Get-PnpDevice | Where-Object {$_.FriendlyName -like "*OBS*"}
   ```
4. Si el driver aparece como deshabilitado, habilítalo desde el Administrador de dispositivos

### Error: "No se puede conectar al dispositivo Android"

**Síntomas**: La app Windows no puede establecer conexión con Android.

**Soluciones**:
- **Modo WiFi**:
  1. Verifica que ambos dispositivos estén en la misma red WiFi
  2. Verifica que el firewall de Windows no esté bloqueando el puerto (por defecto 443)
  3. Verifica la IP configurada en ambas apps
  4. Prueba hacer ping desde Windows a la IP de Android

- **Modo USB**:
  1. Verifica que ADB esté instalado: `adb version`
  2. Verifica que el dispositivo esté conectado: `adb devices`
  3. Verifica que el port forwarding esté activo: `adb forward --list`
  4. Si no aparece, ejecuta: `adb forward tcp:443 tcp:443`

### Error de certificado TLS

**Síntomas**: Error "certificate verify failed" o similar.

**Soluciones**:
1. Genera un nuevo certificado desde la app Android (Configuración → Certificados → Regenerar)
2. Escanea el QR code nuevamente o copia el archivo de certificado
3. Asegúrate de usar el certificado correcto en la app Windows

### Video con lag o frames perdidos

**Síntomas**: El video se ve entrecortado o con retraso.

**Soluciones**:
1. Reduce la resolución o FPS en la configuración de Android
2. Verifica la velocidad de tu conexión WiFi (recomendado mínimo 5 Mbps)
3. En modo USB, verifica que el cable USB soporte transferencia de datos (no solo carga)
4. Cierra otras aplicaciones que usen ancho de banda

### La app Android se cierra inesperadamente

**Síntomas**: La app se cierra al iniciar la transmisión.

**Soluciones**:
1. Verifica que tengas permisos de cámara otorgados
2. Verifica los logs de Android Studio para ver el error específico
3. Reinicia el dispositivo Android
4. Verifica que tu dispositivo soporte codificación H.264 por hardware

### Error: "MediaCodec no disponible"

**Síntomas**: Error al iniciar la codificación de video.

**Soluciones**:
1. Tu dispositivo puede no soportar codificación H.264 por hardware
2. Verifica que tu Android tenga API 24 o superior
3. Prueba con otro dispositivo Android si es posible

### El preview no se muestra en la app Windows

**Síntomas**: La app Windows está conectada pero no muestra video.

**Soluciones**:
1. Verifica que los frames estén llegando (revisa los logs)
2. Verifica que OpenCV esté instalado correctamente
3. Prueba reiniciar la app Windows
4. Verifica que el formato de video sea compatible

### Problemas con pyvirtualcam

**Síntomas**: Error al inicializar la cámara virtual.

**Soluciones**:
1. Verifica que OBS-VirtualCam esté instalado
2. Verifica que ninguna otra aplicación esté usando OBS-Camera
3. Reinicia la app Windows
4. Si el problema persiste, reinstala OBS-VirtualCam

### ADB no reconoce el dispositivo

**Síntomas**: `adb devices` muestra "unauthorized" o no muestra el dispositivo.

**Soluciones**:
1. Desconecta y reconecta el cable USB
2. En Android, acepta el diálogo de autorización de depuración USB
3. Verifica que la depuración USB esté habilitada en Opciones de desarrollador
4. Prueba con otro cable USB
5. En algunos dispositivos, selecciona "Transferencia de archivos" en el modo USB

### Puerto 443 ya está en uso

**Síntomas**: Error al iniciar el servidor en Android o cliente en Windows.

**Soluciones**:
1. Cambia el puerto en la configuración (usa otro puerto como 8443, 9443)
2. Verifica qué aplicación está usando el puerto:
   ```powershell
   netstat -ano | findstr :443
   ```
3. Cierra la aplicación que está usando el puerto o cambia el puerto de VanCamera

## Logs y Debugging

### Android

Los logs se pueden ver en Android Studio:
1. Abre Android Studio
2. Conecta tu dispositivo
3. Ve a la pestaña "Logcat"
4. Filtra por "VanCamera" o el tag de tu aplicación

### Windows

Los logs se muestran en la consola de PowerShell donde ejecutaste `python main.py`.

Para más información de debug, puedes habilitar logging detallado editando `config_manager.py`.

## Obtener Ayuda

Si el problema persiste:
1. Revisa los logs de ambas aplicaciones
2. Verifica que todos los requisitos estén instalados correctamente
3. Consulta los issues en el repositorio del proyecto
4. Crea un nuevo issue con:
   - Descripción detallada del problema
   - Pasos para reproducirlo
   - Logs relevantes
   - Información del sistema (versión de Android, Windows, Python)
