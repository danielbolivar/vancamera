# Troubleshooting

## Quick Reference

| Problem | Likely Cause | Solution |
|---------|--------------|----------|
| No devices found | ADB not installed | [Install ADB](#adb-issues) |
| "ADB not found" right after installing | Old app versions only looked in PATH | Update VanCamera (fixed: the bundled `adb.exe` is used directly) |
| Device unauthorized | USB debugging not accepted | Accept prompt on phone |
| Connection refused | Android not streaming | Start streaming on Android first |
| OBS-Camera not available | Driver not installed | [Install OBS-VirtualCam](#obs-virtualcam-issues) |
| WiFi device not appearing | mDNS blocked | Use **Add by IP…** or USB mode |
| Same phone listed twice | Old app versions | Update both apps (fixed) |
| Video freezes on WiFi | Wi-Fi power save / weak signal | Update both apps; keep *Auto-reconnect* on |
| Stream stops when the screen turns off | Old app versions | Update the Android app (fixed: streaming runs in the background) |
| Phone gets hot | Long sessions, preview on, charging | See [Heat and battery](#heat-and-battery) |
| High latency | Network congestion | Use USB mode |
| Black screen in apps | App cache | Restart the video app |

---

## ADB Issues

### "No devices found"

1. **Check USB cable** - Use a data cable, not charge-only
2. **Check USB Debugging** - Must be enabled in Developer Options
3. **Check ADB installation**:
   ```powershell
   adb version
   ```
4. **Restart ADB server**:
   ```powershell
   adb kill-server
   adb start-server
   adb devices
   ```

### "device unauthorized"

1. Look at your phone screen
2. Accept the "Allow USB debugging?" prompt
3. Check "Always allow from this computer"

### ADB not found

VanCamera looks for `adb` in this order, so no logoff/reboot is needed after installing:

1. The `VANCAMERA_ADB` environment variable (full path to `adb.exe`)
2. `platform-tools\adb.exe` next to `VanCamera.exe` (installed by the installer)
3. The current `PATH`, then the `PATH` stored in the registry
4. `%ANDROID_HOME%`, `%ANDROID_SDK_ROOT%`, `%LOCALAPPDATA%\Android\Sdk`, `C:\platform-tools`

If it is still not found:

1. Download [Platform Tools](https://developer.android.com/studio/releases/platform-tools)
2. Extract to `C:\platform-tools`
3. Click **Refresh** in VanCamera

---

## OBS-VirtualCam Issues

### "OBS-Camera not available"

1. **Reinstall as Administrator**:
   - Download [v2.0.5](https://github.com/Fenrirthviti/obs-virtual-cam/releases/tag/v2.0.5)
   - Right-click → Run as Administrator
   - Restart PC

2. **Verify installation**:
   ```powershell
   Get-PnpDevice | Where-Object {$_.FriendlyName -like "*OBS*"}
   ```

### Camera shows black in Discord/Zoom

1. Close Discord/Zoom completely
2. Start VanCamera and connect
3. Reopen Discord/Zoom
4. Select "OBS-Camera"

---

## Connection Issues

### WiFi device not appearing

1. **Check same network** - Both devices on same WiFi
2. **Check mDNS** - Usually blocked on corporate/university networks
3. **Add by IP** - Click **Add by IP…** and type the address shown on the phone
4. **Use USB instead** - Always works

See [WiFi Connection](CONNECTION_WIFI.md#manual-ip-enterprise--university-networks).

### Video freezes after a few seconds (WiFi)

Fixed in this version: the phone keeps Wi-Fi out of power-save while streaming, drops frames
instead of queueing them on a slow network, and the PC reconnects by itself when the link stalls.
If it still happens, move closer to the router or use USB.

### Stream stops when the phone screen turns off

Fixed in this version: streaming runs in a foreground service. Some manufacturers (Xiaomi,
Huawei, Samsung "Deep sleeping apps", OnePlus...) still kill background apps aggressively:
set VanCamera's battery usage to **Unrestricted** / "Don't optimize" in the app settings.

### Connection refused

1. **Start Android first** - Tap "Start streaming"
2. **Wait for "Waiting for the PC"** - Then connect from Windows (with *Auto-reconnect* on,
   Windows keeps retrying until the phone is ready)
3. **Check firewall** - Port 8443 must be open

### High latency

| Cause | Solution |
|-------|----------|
| WiFi congestion | Use USB mode |
| Weak signal | Move closer to router |
| Background apps | Close other apps |

---

## Video Quality Issues

### Choppy video

1. Check WiFi signal strength
2. Close bandwidth-heavy apps
3. Try USB mode

### Wrong orientation

1. Ensure phone orientation matches preview
2. Lock rotation if needed
3. Restart streaming

---

## Heat and battery

The app now does much less work than before (720p capture instead of the largest 16:9 size,
30 fps cap, no per-pixel conversion, camera off when no PC is connected). To reduce heat further:

1. **Turn the preview off** (eye button) or simply lock the phone while streaming
2. **Use USB** - Wi-Fi radio at full power heats the phone more than a cable
3. **Avoid fast charging while streaming** - charging is a major heat source
4. **Remove the case** for long calls

---

## Python Issues

### pip install fails

Try installing av separately:
```powershell
pip install av --no-binary av
```

### Import errors

Ensure you're in the `windows` directory:
```powershell
cd vancamera\windows
pip install -r requirements.txt
python main.py
```
