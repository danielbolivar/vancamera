# Design Decisions

This document explains the key technical decisions made in VanCamera.

## Summary Table

| Decision | Choice | Why | Alternatives Considered |
|----------|--------|-----|------------------------|
| Encryption | TLS 1.3 | Security on public WiFi | Plain TCP, DTLS |
| Video Codec | H.264 HW | Low latency, battery efficient | VP8, MJPEG, VP9 |
| Server Location | Android | Simpler NAT, static local IP | Windows as server |
| Virtual Camera | OBS-VirtualCam Legacy | DirectShow support, standalone | pyvirtualcam, NDI |
| Discovery | mDNS + USB polling + manual IP | Zero-config standard, with a fallback for managed networks | UDP broadcast, subnet scan |
| Background streaming | Camera foreground service | Survives screen off / app closed | Keep screen on (drains battery, heats the phone) |
| Slow network | Bounded queue, drop to next keyframe | Latency stays bounded | Unbounded buffering (grows lag, freezes) |
| UI Framework | CustomTkinter | Native look, easy to use | PyQt, Electron |

---

## TLS 1.3 for Encryption

**Why**: Video streams contain personal/private content. On public networks (university, coffee shops), unencrypted video could be intercepted.

**TLS 1.3 benefits**:
- Strongest encryption standard
- Built-in to Python and Android
- No additional dependencies
- Fast handshake (1-RTT)

---

## H.264 Hardware Encoding

**Why**: Software encoding drains battery and adds latency. Android's MediaCodec API provides hardware encoding on virtually all devices.

**Benefits**:
- 5-10x lower battery usage than software
- Sub-frame encoding latency
- Universal Android support (API 16+)

---

## Android as Server

**Why**: NAT traversal is simpler when the mobile device hosts the server.

**Reasoning**:
- Android has a stable local IP on WiFi
- No need for port forwarding on the router
- USB mode uses ADB port forwarding (works everywhere)
- Windows can be behind corporate firewalls

---

## OBS-VirtualCam Legacy

**Why**: Maximum compatibility with video applications.

**Benefits**:
- Works with DirectShow (Discord, Zoom, Teams, etc.)
- No OBS Studio installation required
- Standalone installer
- Well-tested, stable driver

**Tradeoff**: Requires separate driver installation.

---

## mDNS for WiFi Discovery

**Why**: Industry standard for local service discovery (like Chromecast, AirPlay).

**How it works**:
1. Android publishes `_vancamera._tcp.local` service
2. Windows listens with Zeroconf library
3. Devices appear automatically in dropdown

**Limitation**: mDNS is often blocked on corporate/university networks. The phone shows its IP
address and Windows can add it manually; USB always works. Windows keys Wi-Fi devices by a stable
id from the TXT record, so the same phone is never listed twice.

---

## Foreground Service Instead of Keeping the Screen On

**Why**: The stream used to die when the screen turned off, because the camera was tied to the
activity. Keeping the screen on would fix that but the display is one of the biggest power and
heat sources. A camera foreground service keeps the camera legally in use with the screen off and
after the app is closed, and shows a notification so the user always knows the camera is active.

---

## Power and Heat

The phone does the least work that still produces the stream:

| Measure | Effect |
|---------|--------|
| Capture at the encoded size (720p) | The old selector could make the ISP produce 1080p/4K frames that were then cropped |
| Cap camera at 30 fps (AE FPS range + limiter) | Some sensors run at 60 fps by default |
| Bulk row copies into the codec buffer | Replaces ~1.4 M `ByteBuffer.get()` calls and a 1.4 MB allocation per frame |
| MediaCodec async mode, single camera thread | No coroutine per frame, no concurrent codec access |
| Camera/encoder only while a PC is connected | Idle "waiting" costs almost nothing |
| Optional preview | The PC does not need the phone's screen |
| Wake / Wi-Fi locks only while a PC is connected | No battery drain while idle |

---

## USB Polling Every 2 Seconds

**Why**: Balance between responsiveness and CPU usage.

**Reasoning**:
- `adb devices` is fast (<100ms)
- 2s is responsive enough for plug-in detection
- Lower intervals waste CPU cycles
- Higher intervals feel sluggish
