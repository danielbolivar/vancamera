# Android Installation

## Requirements

| Requirement | Minimum |
|-------------|---------|
| Android Version | 7.0 (API 24) |
| Camera | Front or back |
| Storage | 50 MB |

## Build from Source

### 1. Install Android Studio

Download from [developer.android.com/studio](https://developer.android.com/studio)

### 2. Clone Repository

```bash
git clone https://github.com/user/vancamera.git
cd vancamera/android
```

### 3. Open in Android Studio

1. Open Android Studio
2. Select "Open an existing project"
3. Navigate to the `android` folder
4. Wait for Gradle sync to complete

### 4. Build APK

1. Build → Build Bundle(s) / APK(s) → Build APK(s)
2. APK will be in `app/build/outputs/apk/debug/`

### 5. Install on Device

Option A: Connect via USB
```bash
adb install app/build/outputs/apk/debug/app-debug.apk
```

Option B: Transfer APK and install manually

## Permissions

The app requires these permissions:

| Permission | Purpose |
|------------|---------|
| CAMERA | Video capture |
| INTERNET | Network streaming |

Grant permissions when prompted on first launch.

## Enable USB Debugging (for USB mode)

1. **Open Settings** → About Phone
2. **Tap "Build Number"** 7 times until "Developer mode enabled"
3. **Go back** → Developer Options
4. **Enable** "USB Debugging"
5. **Connect phone** to PC via USB
6. **Accept** the debugging authorization prompt

## Verify Installation

1. Launch VanCamera app
2. Grant camera permission
3. You should see camera preview
4. Status shows "Disconnected"

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Camera permission denied | Settings → Apps → VanCamera → Permissions |
| Black preview | Try switching front/back camera |
| Build fails | File → Invalidate Caches and Restart |
| Gradle sync fails | Check internet connection |
