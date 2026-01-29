# Building VanCamera for Android

This guide explains how to build the VanCamera Android app from source.

## Prerequisites

| Requirement | Version | Download |
|-------------|---------|----------|
| JDK | 11 or later | [Adoptium](https://adoptium.net/) |
| Android SDK | API 24+ | Via Android Studio or [Command Line Tools](https://developer.android.com/studio#command-tools) |

**Optional but recommended:**
- [Android Studio](https://developer.android.com/studio) - IDE with GUI build tools

## Quick Build

### Debug Build (No Signing Required)

```bash
cd android
./build_release.sh --debug
```

Output: `app/build/outputs/apk/debug/app-debug.apk`

### Release Build (Requires Signing)

```bash
# First, create a keystore (one-time setup)
./build_release.sh --create-keystore

# Set environment variables
export VANCAMERA_KEYSTORE_PASSWORD='your_keystore_password'
export VANCAMERA_KEY_PASSWORD='your_key_password'

# Build
./build_release.sh
```

Output: `app/build/outputs/apk/release/app-release.apk`

## Creating a Signing Keystore

A keystore is required to sign release builds. This is a one-time setup.

### Using the Build Script

```bash
./build_release.sh --create-keystore
```

You'll be prompted for:
- Keystore password
- Key password
- Your name and organization

### Manual Creation

```bash
keytool -genkey -v \
    -keystore app/keystore/vancamera.jks \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000 \
    -alias vancamera
```

> **Important:** 
> - Back up your keystore file securely!
> - Remember your passwords!
> - You'll need the same keystore to update your app on Google Play

## Build Commands

### Using the Build Script

```bash
# Debug APK (unsigned, for testing)
./build_release.sh --debug

# Release APK (signed)
./build_release.sh

# AAB for Google Play
./build_release.sh --bundle

# Show help
./build_release.sh --help
```

### Using Gradle Directly

```bash
cd android

# Debug build
./gradlew assembleDebug

# Release build (requires signing setup)
./gradlew assembleRelease

# Release bundle for Google Play
./gradlew bundleRelease

# Clean build
./gradlew clean

# List all tasks
./gradlew tasks
```

## Environment Variables

Configure signing via environment variables (recommended for CI/CD):

| Variable | Description | Default |
|----------|-------------|---------|
| `VANCAMERA_KEYSTORE_PATH` | Path to keystore file | `app/keystore/vancamera.jks` |
| `VANCAMERA_KEYSTORE_PASSWORD` | Keystore password | (required) |
| `VANCAMERA_KEY_ALIAS` | Key alias | `vancamera` |
| `VANCAMERA_KEY_PASSWORD` | Key password | (required) |

Example:

```bash
export VANCAMERA_KEYSTORE_PATH="/secure/path/to/my.jks"
export VANCAMERA_KEYSTORE_PASSWORD="my_secure_password"
export VANCAMERA_KEY_ALIAS="my_key"
export VANCAMERA_KEY_PASSWORD="my_key_password"

./gradlew assembleRelease
```

## Build Outputs

| Build Type | Location | Use Case |
|------------|----------|----------|
| Debug APK | `app/build/outputs/apk/debug/app-debug.apk` | Testing, development |
| Release APK | `app/build/outputs/apk/release/app-release.apk` | Direct distribution, sideloading |
| Release AAB | `app/build/outputs/bundle/release/app-release.aab` | Google Play Store |

## Version Configuration

Edit `android/app/build.gradle.kts`:

```kotlin
defaultConfig {
    applicationId = "com.vancamera.android"
    minSdk = 24
    targetSdk = 35
    versionCode = 1        // Increment for each release
    versionName = "1.0.0"  // User-visible version
}
```

**Important for Play Store:**
- `versionCode` must be incremented for every upload
- `versionName` is what users see

## ProGuard / R8

Release builds have code shrinking enabled:

```kotlin
buildTypes {
    release {
        isMinifyEnabled = true      // Enable R8/ProGuard
        isShrinkResources = true    // Remove unused resources
    }
}
```

If you encounter issues with obfuscation, edit `proguard-rules.pro` to add keep rules.

## Project Structure

```
android/
├── app/
│   ├── build.gradle.kts    # App-level build config
│   ├── proguard-rules.pro  # ProGuard/R8 rules
│   ├── keystore/           # Signing keystore (gitignored)
│   │   └── vancamera.jks
│   └── src/
│       └── main/
│           ├── AndroidManifest.xml
│           ├── java/       # Kotlin/Java source
│           └── res/        # Resources
├── build.gradle.kts        # Project-level build config
├── settings.gradle.kts     # Project settings
├── gradle.properties       # Gradle settings
├── build_release.sh        # Build helper script
└── gradlew                 # Gradle wrapper
```

## Installing the APK

### Via ADB

```bash
# Install (replace existing)
adb install -r app/build/outputs/apk/release/app-release.apk

# Install on specific device
adb -s DEVICE_SERIAL install -r app-release.apk
```

### Via File Transfer

1. Copy APK to device (USB, cloud storage, etc.)
2. On device, navigate to the file
3. Tap to install
4. Enable "Install from unknown sources" if prompted

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Android Build

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: 'temurin'
      
      - name: Setup Android SDK
        uses: android-actions/setup-android@v3
      
      - name: Decode keystore
        run: |
          echo "${{ secrets.KEYSTORE_BASE64 }}" | base64 -d > android/app/keystore/vancamera.jks
      
      - name: Build Release APK
        env:
          VANCAMERA_KEYSTORE_PASSWORD: ${{ secrets.KEYSTORE_PASSWORD }}
          VANCAMERA_KEY_PASSWORD: ${{ secrets.KEY_PASSWORD }}
        run: |
          cd android
          chmod +x gradlew
          ./gradlew assembleRelease
      
      - name: Upload APK
        uses: actions/upload-artifact@v4
        with:
          name: VanCamera-Android
          path: android/app/build/outputs/apk/release/*.apk
```

### Storing Keystore in CI

1. Base64 encode your keystore:
   ```bash
   base64 -i vancamera.jks > keystore.b64
   ```

2. Add as GitHub secret: `KEYSTORE_BASE64`

3. Add password secrets: `KEYSTORE_PASSWORD`, `KEY_PASSWORD`

## Troubleshooting

### Build Errors

| Error | Solution |
|-------|----------|
| `JAVA_HOME not set` | Install JDK, set JAVA_HOME environment variable |
| `SDK not found` | Set ANDROID_HOME or install via Android Studio |
| `License not accepted` | Run `sdkmanager --licenses` |
| `Keystore not found` | Create with `--create-keystore` option |
| `Wrong password` | Check VANCAMERA_KEYSTORE_PASSWORD and VANCAMERA_KEY_PASSWORD |

### Runtime Errors

| Error | Solution |
|-------|----------|
| App crashes on start | Check logcat: `adb logcat *:E` |
| Camera not working | Ensure camera permissions granted |
| Network errors | Check network permissions in manifest |

### Common Gradle Issues

```bash
# Clear Gradle cache
./gradlew clean
rm -rf ~/.gradle/caches/

# Update Gradle wrapper
./gradlew wrapper --gradle-version=8.5

# Run with stack trace
./gradlew assembleRelease --stacktrace
```

## Publishing to Google Play

1. **Create AAB:**
   ```bash
   ./build_release.sh --bundle
   ```

2. **Google Play Console:**
   - Go to [play.google.com/console](https://play.google.com/console)
   - Create new app or select existing
   - Go to Release > Production
   - Upload `app-release.aab`
   - Fill in release notes
   - Submit for review

3. **Requirements:**
   - Privacy policy URL
   - App screenshots
   - Feature graphic
   - Content rating questionnaire
   - Target audience declaration

## Security Notes

- **Never commit** your keystore or passwords to git
- Store keystore backup in a **secure location**
- Use **environment variables** for passwords in CI/CD
- Consider using **Google Play App Signing** for additional security
