# Building VanCamera for Windows

This guide explains how to build the VanCamera Windows installer from source.

## Prerequisites

| Requirement | Version | Download |
|-------------|---------|----------|
| Python | 3.8 or later | [python.org](https://www.python.org/downloads/) |
| Inno Setup | 6.x | [jrsoftware.org](https://jrsoftware.org/isdl.php) |
| Internet | - | For downloading dependencies |

## Quick Build

The easiest way to build is using the automated script:

```powershell
cd windows\build
.\build_release.ps1
```

This will:
1. Create a clean Python virtual environment
2. Install all dependencies
3. Download ADB Platform Tools
4. Build the executable with PyInstaller
5. Create the installer with Inno Setup

Output: `windows\build\Output\VanCamera-Setup-x.x.x.exe`

## Manual Build Process

### Step 1: Set Up Python Environment

```powershell
cd windows\build

# Create virtual environment
python -m venv venv

# Activate it
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r ..\requirements.txt
pip install pyinstaller
```

### Step 2: Download External Dependencies

Create the `deps` folder and download:

#### ADB Platform Tools

```powershell
# Download from Google
Invoke-WebRequest -Uri "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile "deps\platform-tools.zip"

# Extract
Expand-Archive -Path "deps\platform-tools.zip" -DestinationPath "deps" -Force

# Clean up
Remove-Item "deps\platform-tools.zip"
```

#### OBS-VirtualCam

1. Download from [GitHub Releases](https://github.com/Fenrirthviti/obs-virtual-cam/releases/tag/v2.0.5)
2. Save as `deps\OBS-VirtualCam-2.0.5-Windows-Installer.exe`

### Step 3: Build Executable

```powershell
# Make sure venv is activated
.\venv\Scripts\Activate.ps1

# Run PyInstaller
pyinstaller --clean vancamera.spec
```

Output: `dist\VanCamera\VanCamera.exe`

### Step 4: Create Installer

```powershell
# Run Inno Setup compiler
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" VanCamera.iss
```

Output: `Output\VanCamera-Setup-1.0.0.exe`

## Build Script Options

The `build_release.ps1` script supports several options:

```powershell
# Build with specific version
.\build_release.ps1 -Version "1.2.0"

# Skip virtual environment creation (faster rebuild)
.\build_release.ps1 -SkipVenv

# Skip dependency download
.\build_release.ps1 -SkipDeps

# Combine options
.\build_release.ps1 -Version "2.0.0" -SkipVenv -SkipDeps
```

## Project Structure

```
windows/
├── build/
│   ├── vancamera.spec      # PyInstaller configuration
│   ├── VanCamera.iss       # Inno Setup script
│   ├── build_release.ps1   # Automated build script
│   ├── icon.ico            # Application icon (optional)
│   ├── deps/               # External dependencies
│   │   ├── platform-tools/ # ADB (downloaded)
│   │   └── OBS-*.exe       # OBS-VirtualCam installer
│   ├── venv/               # Python virtual environment (created)
│   ├── build/              # PyInstaller temp files (created)
│   ├── dist/               # PyInstaller output (created)
│   └── Output/             # Final installer (created)
├── main.py
├── ui_app.py
├── ... (other source files)
└── requirements.txt
```

## Customization

### Changing Version Number

Edit `VanCamera.iss`:

```iss
#define MyAppVersion "1.0.0"
```

Or use the build script parameter:

```powershell
.\build_release.ps1 -Version "2.0.0"
```

### Adding Custom Icon

1. Create an `.ico` file with multiple sizes (16x16, 32x32, 48x48, 256x256)
2. Save as `windows\build\icon.ico`
3. Rebuild - PyInstaller will automatically use it

### Modifying the Installer

Edit `VanCamera.iss` to customize:

- Installation directory
- Shortcuts
- Registry entries
- Pre/post-installation scripts

See [Inno Setup Documentation](https://jrsoftware.org/ishelp/) for details.

## Troubleshooting

### PyInstaller Issues

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Add module to `hiddenimports` in `vancamera.spec` |
| Missing DLL errors | Ensure Visual C++ Redistributable is installed |
| Antivirus blocks EXE | Add exclusion or sign the executable |
| Large EXE size | Review `excludes` in spec file |

### Inno Setup Issues

| Problem | Solution |
|---------|----------|
| ISCC not found | Install Inno Setup 6, verify path |
| Missing files | Run PyInstaller first, check `dist\VanCamera` |
| Admin rights error | Run PowerShell as Administrator |

### Runtime Issues

| Problem | Solution |
|---------|----------|
| App won't start | Check for missing DLLs with Dependency Walker |
| OBS-Camera not found | Reinstall OBS-VirtualCam as Administrator |
| ADB not found | Verify `platform-tools` in installation folder |

## CI/CD Integration

For automated builds (GitHub Actions, etc.):

```yaml
# Example GitHub Actions workflow
jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install Inno Setup
        run: choco install innosetup -y
      
      - name: Build installer
        run: |
          cd windows\build
          .\build_release.ps1 -Version "${{ github.ref_name }}"
      
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: VanCamera-Windows-Installer
          path: windows\build\Output\*.exe
```

## What the Installer Does

When a user runs the installer:

1. **Copies files** to `C:\Program Files\VanCamera\`
2. **Installs ADB** to `C:\Program Files\VanCamera\platform-tools\`
3. **Adds ADB to PATH** (user environment variable)
4. **Installs OBS-VirtualCam** driver (if selected)
5. **Creates shortcuts** in Start Menu and Desktop
6. **Registers uninstaller** in Windows Apps & Features

On uninstall:
- Removes all installed files
- Removes ADB from PATH
- Cleans up config files from `%LOCALAPPDATA%\VanCamera`
- Note: OBS-VirtualCam is NOT uninstalled (may be used by other apps)
