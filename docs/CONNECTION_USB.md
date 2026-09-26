# USB Connection

## Overview

USB mode provides the lowest latency and most reliable connection. It uses ADB (Android Debug Bridge) to create a TCP tunnel over the USB cable.

## How It Works

```mermaid
sequenceDiagram
    participant W as WindowsApp
    participant ADB as ADB
    participant A as Android

    loop Every 2 seconds
        W->>ADB: adb devices
        ADB-->>W: List of devices
    end
    W->>W: Show device in dropdown
    Note over W: User selects device
    W->>ADB: adb -s SERIAL forward tcp:8443 tcp:8443
    ADB-->>W: Forward created
    W->>W: Connect to 127.0.0.1:8443
    ADB->>A: Tunnel traffic to :8443
    A->>W: Encrypted H.264 stream
```

## ADB Port Forwarding

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Windows App    │      │    USB Cable    │      │     Android     │
│                 │      │                 │      │                 │
│ Connect to      │      │   ADB Tunnel    │      │  TLS Server     │
│ 127.0.0.1:8443 ─┼─────▶│ tcp:8443 ──────▶│─────▶│  :8443          │
│                 │      │                 │      │                 │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

## Why 127.0.0.1?

- ADB creates a local port that tunnels to Android
- Windows connects to `localhost:8443`
- ADB forwards all traffic through USB
- No need to know Android's actual IP

## Requirements

| Requirement | Details |
|-------------|---------|
| USB cable | Must be data-capable (not charge-only) |
| USB Debugging | Enabled in Developer Options |
| ADB | Bundled with the installer (or any platform-tools install) |

## Setup ADB

The Windows installer ships `adb.exe` in `{install dir}\platform-tools`, and the app uses that
copy directly, so USB mode works right after installing (no logoff or reboot).

When running from source, VanCamera also finds adb in `PATH`, in the registry `PATH`,
`%ANDROID_HOME%`, `%ANDROID_SDK_ROOT%`, `%LOCALAPPDATA%\Android\Sdk` or `C:\platform-tools`,
or wherever the `VANCAMERA_ADB` environment variable points. To install it manually:

1. Download [Android SDK Platform Tools](https://developer.android.com/studio/releases/platform-tools)
2. Extract to a folder (e.g., `C:\platform-tools`)
3. Click **Refresh** in VanCamera

## Enable USB Debugging

1. Settings → About Phone
2. Tap "Build Number" 7 times
3. Settings → Developer Options
4. Enable "USB Debugging"
5. Connect phone and accept the prompt

## Pros and Cons

| Pros | Cons |
|------|------|
| Lowest latency | Requires cable |
| Most reliable | Phone stays tethered |
| Works anywhere | One device at a time |
| No network needed | Requires ADB setup |
| Always works | - |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No devices found" | Check USB cable is data-capable |
| "unauthorized" | Accept USB debugging prompt on phone |
| ADB not found | Reinstall VanCamera, or see [Troubleshooting](TROUBLESHOOTING.md#adb-not-found) |
| Port forward fails | Restart ADB: `adb kill-server` |
