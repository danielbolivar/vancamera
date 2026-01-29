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

1. Download [Android SDK Platform Tools](https://developer.android.com/studio/releases/platform-tools)
2. Extract to `C:\platform-tools`
3. Add to PATH:
   - Search "Environment Variables" in Windows
   - Edit PATH → Add `C:\platform-tools`

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
| "No devices found" | Check ADB installation, USB cable |
| pip install fails | Try `pip install av --no-binary av` |
| High CPU usage | Normal for video decoding |
| Black screen in Discord | Restart Discord after connecting |
