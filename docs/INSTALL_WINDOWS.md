# Windows Installation

## Requirements

| Requirement | Minimum |
|-------------|---------|
| Windows | 10 or later |
| Python | 3.8+ |
| OBS-VirtualCam | Legacy v2.0.5 |
| ADB | For USB mode |

## Step 1: Install OBS-VirtualCam

1. Download [OBS-VirtualCam Legacy v2.0.5](https://github.com/Fenrirthviti/obs-virtual-cam/releases/tag/v2.0.5)
2. Run installer **as Administrator**
3. Accept certificate if prompted
4. Restart PC if required

### Verify Installation

```powershell
Get-PnpDevice | Where-Object {$_.FriendlyName -like "*OBS*"}
```

You should see "OBS-Camera" listed.

## Step 2: Install ADB (for USB mode)

The installer already includes ADB and VanCamera finds it immediately (no logoff or reboot
needed). When running from source:

1. Download [Android SDK Platform Tools](https://developer.android.com/studio/releases/platform-tools)
2. Extract to `C:\platform-tools` (found automatically), or add the folder to PATH

### Verify ADB

```powershell
adb version
```

## Step 3: Install Python Dependencies

```powershell
cd vancamera\windows
pip install -r requirements.txt
```

## Step 4: Run VanCamera

```powershell
python main.py
```

## Using the App

1. Pick your phone in the **Phone** list (USB and Wi-Fi phones appear automatically), or click
   **Add by IP…** and type the address shown on the phone.
2. Click **Connect**. The status pill turns green and shows fps / bitrate.
3. **Show preview**: turn it off to save CPU; the virtual camera keeps working.
4. **Auto-reconnect**: on by default; after a Wi-Fi drop the app reconnects by itself and keeps
   the virtual camera open so your video call does not lose the camera.

## Configure Video Apps

### Discord

1. Settings → Voice & Video
2. Camera → Select "OBS-Camera"

### Zoom

1. Settings → Video
2. Camera → Select "OBS-Camera"

### Microsoft Teams

1. Settings → Devices
2. Camera → Select "OBS-Camera"

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "OBS-Camera not available" | Reinstall OBS-VirtualCam as Admin |
| "No devices found" | Check USB cable / USB debugging, or use **Add by IP…** for Wi-Fi |
| "Virtual camera unavailable" hint | Install OBS-VirtualCam 2.0.5 and restart VanCamera |
| pip install fails | Try `pip install av --no-binary av` |
| High CPU usage | Turn off **Show preview** |
| Black screen in Discord | Restart Discord after connecting |
