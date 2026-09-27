# VanCamera

Use your Android phone as a high-quality, low-latency webcam for Windows. Secure, open-source, works natively with Discord, Zoom, and Teams.

> You can download and install VanCamera for Windows and Android [here](https://github.com/danielbolivar/vancamera/releases/tag/1.0.0)

> [!NOTE]
> Found a problem? Please report it [here](https://github.com/danielbolivar/vancamera/issues).

## Features

- **Auto-Discovery** - Devices appear automatically (USB and WiFi)
- **Works with the app closed** - Streaming runs in a foreground service: lock the phone, switch apps or swipe VanCamera away and the PC keeps receiving video
- **Cool and battery friendly** - Camera only runs while a PC is connected (or the preview is on screen), capped at 720p/30 fps, optional preview-off mode
- **Survives network hiccups** - The PC reconnects automatically; slow Wi-Fi drops frames instead of freezing
- **Works on office/university Wi-Fi** - Add the phone by IP when the network blocks discovery
- **Low Latency** - Hardware H.264 encoding, optimized for real-time
- **Secure** - TLS 1.3 encryption, safe for public networks
- **Native** - Works with any DirectShow app (Discord, Zoom, Teams)
- **Simple** - One-click connect, no configuration needed

## Quick Start

### 1. Install Prerequisites

**Windows:**
- Install [OBS-VirtualCam Legacy v2.0.5](https://github.com/Fenrirthviti/obs-virtual-cam/releases/tag/2.0.5)
- Install [Python 3.8+](https://www.python.org/downloads/) (only when running from source)
- [ADB](https://developer.android.com/studio/releases/platform-tools) for USB mode (bundled with the installer and found automatically, no reboot needed)

**Android:**
- Build and install the app from `android/` folder

### 2. Run

**Android:**
1. Launch VanCamera
2. Tap "Start streaming" (the screen shows the phone's IP address)
3. You can now lock the phone or close the app; stop it from the notification

**Windows:**
```powershell
cd windows
pip install -r requirements.txt
python main.py
```

### 3. Connect

1. Select your device from the dropdown (or click **Add by IP…** and type the address shown on the phone)
2. Click **Connect**
3. Open Discord/Zoom → Select "OBS-Camera"

## Connection Modes

| Mode | Best For | Setup |
|------|----------|-------|
| **USB** | Lowest latency, most reliable | Connect USB cable, enable USB debugging |
| **WiFi** | Wireless freedom | Same network, device appears when streaming |
| **WiFi (manual IP)** | Office / university networks that block discovery | Click "Add by IP…" and type the address shown on the phone |

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/ARCHITECTURE.md) | System overview and components |
| [Design Decisions](docs/DESIGN_DECISIONS.md) | Why we chose TLS, H.264, etc. |
| [Protocol](docs/PROTOCOL.md) | Wire protocol specification |
| [USB Connection](docs/CONNECTION_USB.md) | How USB mode works |
| [WiFi Connection](docs/CONNECTION_WIFI.md) | How WiFi mode works |
| [Install Android](docs/INSTALL_ANDROID.md) | Android setup guide |
| [Install Windows](docs/INSTALL_WINDOWS.md) | Windows setup guide |
| [Build Android](docs/BUILD_ANDROID.md) | Building Android APK from source |
| [Build Windows](docs/BUILD_WINDOWS.md) | Building Windows installer from source |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and fixes |

## Building from Source

Want to build the installers yourself? See the build documentation:

| Platform | Build Guide | Output |
|----------|-------------|--------|
| Windows | [BUILD_WINDOWS.md](docs/BUILD_WINDOWS.md) | `VanCamera-Setup-x.x.x.exe` |
| Android | [BUILD_ANDROID.md](docs/BUILD_ANDROID.md) | `app-release.apk` |

### Quick Build Commands

**Windows:**
```powershell
cd windows\build
.\build_release.ps1
```

**Android:**
```bash
cd android
./build_release.sh
```

## Requirements

### Android
- Android 7.0+ (API 24)
- Camera (front or back)

### Windows
- Windows 10+
- Python 3.8+
- OBS-VirtualCam Legacy v2.0.5
- ADB (for USB mode, bundled with the installer)

## Running the Tests

**Android** (JVM unit tests: YUV conversion, packet framing, frame dropping, FPS limiting):
```bash
cd android
./gradlew testDebugUnitTest
```

**Windows** (includes end-to-end tests against a fake phone that streams real H.264 over TLS):
```bash
cd windows
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests
```

## License

MIT License - See [LICENSE](LICENSE)

## Contributing

Contributions welcome! Please read the architecture docs before submitting PRs.
