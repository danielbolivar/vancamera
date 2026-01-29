# Design Decisions

This document explains the key technical decisions made in VanCamera.

## Summary Table

| Decision | Choice | Why | Alternatives Considered |
|----------|--------|-----|------------------------|
| Encryption | TLS 1.3 | Security on public WiFi | Plain TCP, DTLS |
| Video Codec | H.264 HW | Low latency, battery efficient | VP8, MJPEG, VP9 |
| Server Location | Android | Simpler NAT, static local IP | Windows as server |
| Virtual Camera | OBS-VirtualCam Legacy | DirectShow support, standalone | pyvirtualcam, NDI |
| Discovery | mDNS + USB polling | Zero-config standard | Manual IP, UDP broadcast |
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

**Limitation**: mDNS may be blocked on some corporate networks. USB always works.

---

## USB Polling Every 2 Seconds

**Why**: Balance between responsiveness and CPU usage.

**Reasoning**:
- `adb devices` is fast (<100ms)
- 2s is responsive enough for plug-in detection
- Lower intervals waste CPU cycles
- Higher intervals feel sluggish
