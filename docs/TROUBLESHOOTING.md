# Troubleshooting

## Quick Reference

| Problem | Likely Cause | Solution |
|---------|--------------|----------|
| No devices found | ADB not installed | [Install ADB](#adb-issues) |
| Device unauthorized | USB debugging not accepted | Accept prompt on phone |
| Connection refused | Android not streaming | Start streaming on Android first |
| OBS-Camera not available | Driver not installed | [Install OBS-VirtualCam](#obs-virtualcam-issues) |
| WiFi device not appearing | mDNS blocked | Use USB mode |
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

1. Download [Platform Tools](https://developer.android.com/studio/releases/platform-tools)
2. Extract to `C:\platform-tools`
3. Add to PATH environment variable
4. Restart terminal/IDE

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
2. **Check mDNS** - May be blocked on corporate networks
3. **Use USB instead** - Always works

### Connection refused

1. **Start Android first** - Tap "Start streaming"
2. **Wait for "Listening..."** - Then connect from Windows
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
