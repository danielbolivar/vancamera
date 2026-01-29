#!/bin/bash
#
# VanCamera Android Release Build Script
#
# This script builds the Android app for release distribution.
#
# Usage:
#   ./build_release.sh              # Build APK (requires keystore)
#   ./build_release.sh --debug      # Build debug APK (no signing required)
#   ./build_release.sh --bundle     # Build AAB for Google Play
#   ./build_release.sh --create-keystore  # Create new signing keystore
#
# Environment variables for signing:
#   VANCAMERA_KEYSTORE_PATH      - Path to keystore file (default: app/keystore/vancamera.jks)
#   VANCAMERA_KEYSTORE_PASSWORD  - Keystore password
#   VANCAMERA_KEY_ALIAS          - Key alias (default: vancamera)
#   VANCAMERA_KEY_PASSWORD       - Key password
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Default keystore location
KEYSTORE_DIR="$SCRIPT_DIR/app/keystore"
KEYSTORE_FILE="$KEYSTORE_DIR/vancamera.jks"

print_header() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║           VanCamera Android Release Build                     ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "\n${CYAN}==> $1${NC}"
}

print_success() {
    echo -e "${GREEN}    ✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}    ⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}    ✗ $1${NC}"
}

create_keystore() {
    print_step "Creating signing keystore..."
    
    mkdir -p "$KEYSTORE_DIR"
    
    if [ -f "$KEYSTORE_FILE" ]; then
        print_warning "Keystore already exists at: $KEYSTORE_FILE"
        read -p "    Overwrite? (y/N): " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            exit 0
        fi
        rm "$KEYSTORE_FILE"
    fi
    
    echo ""
    echo "    Creating new keystore. You will be prompted for:"
    echo "    - Keystore password (remember this!)"
    echo "    - Key password (can be same as keystore password)"
    echo "    - Your name and organization info"
    echo ""
    
    keytool -genkey -v \
        -keystore "$KEYSTORE_FILE" \
        -keyalg RSA \
        -keysize 2048 \
        -validity 10000 \
        -alias vancamera
    
    if [ -f "$KEYSTORE_FILE" ]; then
        print_success "Keystore created at: $KEYSTORE_FILE"
        echo ""
        echo -e "${YELLOW}    IMPORTANT: Back up your keystore file and remember your passwords!${NC}"
        echo -e "${YELLOW}    You will need them to update your app on Google Play.${NC}"
        echo ""
        echo "    To build a release APK, set these environment variables:"
        echo "    export VANCAMERA_KEYSTORE_PASSWORD='your_password'"
        echo "    export VANCAMERA_KEY_PASSWORD='your_password'"
    else
        print_error "Failed to create keystore"
        exit 1
    fi
}

check_java() {
    print_step "Checking Java installation..."
    
    if ! command -v java &> /dev/null; then
        print_error "Java not found. Please install JDK 11 or later."
        exit 1
    fi
    
    java_version=$(java -version 2>&1 | head -n 1)
    print_success "Found: $java_version"
}

check_keystore() {
    # Check for keystore file
    local keystore_path="${VANCAMERA_KEYSTORE_PATH:-$KEYSTORE_FILE}"
    
    if [ ! -f "$keystore_path" ]; then
        print_warning "Keystore not found at: $keystore_path"
        echo ""
        echo "    To create a keystore, run:"
        echo "    ./build_release.sh --create-keystore"
        echo ""
        echo "    Or to build without signing (debug):"
        echo "    ./build_release.sh --debug"
        echo ""
        exit 1
    fi
    
    # Check for passwords
    if [ -z "$VANCAMERA_KEYSTORE_PASSWORD" ] || [ -z "$VANCAMERA_KEY_PASSWORD" ]; then
        print_warning "Signing passwords not set"
        echo ""
        echo "    Please set environment variables:"
        echo "    export VANCAMERA_KEYSTORE_PASSWORD='your_password'"
        echo "    export VANCAMERA_KEY_PASSWORD='your_password'"
        echo ""
        exit 1
    fi
    
    print_success "Keystore found and configured"
}

build_debug() {
    print_step "Building debug APK..."
    
    ./gradlew clean assembleDebug
    
    local apk_path="app/build/outputs/apk/debug/app-debug.apk"
    if [ -f "$apk_path" ]; then
        local size=$(du -h "$apk_path" | cut -f1)
        print_success "Debug APK built: $apk_path ($size)"
    else
        print_error "Build failed - APK not found"
        exit 1
    fi
}

build_release() {
    print_step "Building release APK..."
    
    check_keystore
    
    ./gradlew clean assembleRelease
    
    local apk_path="app/build/outputs/apk/release/app-release.apk"
    if [ -f "$apk_path" ]; then
        local size=$(du -h "$apk_path" | cut -f1)
        echo ""
        print_success "Release APK built successfully!"
        echo ""
        echo "    Location: $apk_path"
        echo "    Size: $size"
        echo ""
    else
        print_error "Build failed - APK not found"
        exit 1
    fi
}

build_bundle() {
    print_step "Building release bundle (AAB) for Google Play..."
    
    check_keystore
    
    ./gradlew clean bundleRelease
    
    local aab_path="app/build/outputs/bundle/release/app-release.aab"
    if [ -f "$aab_path" ]; then
        local size=$(du -h "$aab_path" | cut -f1)
        echo ""
        print_success "Release bundle built successfully!"
        echo ""
        echo "    Location: $aab_path"
        echo "    Size: $size"
        echo ""
        echo "    Upload this file to Google Play Console."
    else
        print_error "Build failed - AAB not found"
        exit 1
    fi
}

show_help() {
    echo "VanCamera Android Build Script"
    echo ""
    echo "Usage: ./build_release.sh [option]"
    echo ""
    echo "Options:"
    echo "  (no option)         Build signed release APK"
    echo "  --debug             Build debug APK (no signing required)"
    echo "  --bundle            Build AAB for Google Play"
    echo "  --create-keystore   Create new signing keystore"
    echo "  --help              Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  VANCAMERA_KEYSTORE_PATH       Path to keystore (default: app/keystore/vancamera.jks)"
    echo "  VANCAMERA_KEYSTORE_PASSWORD   Keystore password"
    echo "  VANCAMERA_KEY_ALIAS           Key alias (default: vancamera)"
    echo "  VANCAMERA_KEY_PASSWORD        Key password"
}

# Main
print_header
check_java

case "${1:-}" in
    --debug)
        build_debug
        ;;
    --bundle)
        build_bundle
        ;;
    --create-keystore)
        create_keystore
        ;;
    --help|-h)
        show_help
        ;;
    "")
        build_release
        ;;
    *)
        print_error "Unknown option: $1"
        show_help
        exit 1
        ;;
esac
