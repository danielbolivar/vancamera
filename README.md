# VanCamera

Use your Android phone as a high-quality, low-latency webcam for Windows. Secure, open-source, works natively with Discord, Zoom, and Teams.

## Features

- **Auto-Discovery** - Devices appear automatically (USB and WiFi)
- **Low Latency** - Hardware H.264 encoding, optimized for real-time
- **Secure** - TLS 1.3 encryption, safe for public networks
- **Native** - Works with any DirectShow app (Discord, Zoom, Teams)
- **Simple** - One-click connect, no configuration needed

## Quick Start

### 1. Install Prerequisites

**Windows:**
- Install [OBS-VirtualCam Legacy v2.0.5](https://github.com/Fenrirthviti/obs-virtual-cam/releases/tag/v2.0.5)
- Install [Python 3.8+](https://www.python.org/downloads/)
- Install [ADB](https://developer.android.com/studio/releases/platform-tools) (for USB mode)

**Android:**
- Build and install the app from `android/` folder

### 2. Run

**Android:**
1. Launch VanCamera
2. Tap "Start streaming"

**Windows:**
```powershell
cd windows
pip install -r requirements.txt
python main.py
```

### 3. Connect

1. Select your device from the dropdown
2. Click "Start Receiving"
3. Open Discord/Zoom → Select "OBS-Camera"

## Connection Modes

| Mode | Best For | Setup |
|------|----------|-------|
| **USB** | Lowest latency, most reliable | Connect USB cable, enable USB debugging |
| **WiFi** | Wireless freedom | Same network, device appears when streaming |

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
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and fixes |

## Requirements

### Android
- Android 7.0+ (API 24)
- Camera (front or back)

### Windows
- Windows 10+
- Python 3.8+
- OBS-VirtualCam Legacy v2.0.5
- ADB (for USB mode)

## License

MIT License - See [LICENSE](LICENSE)

## Contributing

Contributions welcome! Please read the architecture docs before submitting PRs.
