#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUTPUT_DIR="$PROJECT_DIR/dist"
STAGING_DIR="$OUTPUT_DIR/staging"
APP_DIR="$STAGING_DIR/ChargePilotAgent.app"
VERSION=0.1.0
ARM64_BUILD="$PROJECT_DIR/.build/dmg-arm64"
X86_64_BUILD="$PROJECT_DIR/.build/dmg-x86_64"

mkdir -p "$STAGING_DIR"
rm -f "$STAGING_DIR/ChargePilotAgent"
swift build \
    --package-path "$PROJECT_DIR" \
    --scratch-path "$ARM64_BUILD" \
    --triple arm64-apple-macosx13.0 \
    -c release
swift build \
    --package-path "$PROJECT_DIR" \
    --scratch-path "$X86_64_BUILD" \
    --triple x86_64-apple-macosx13.0 \
    -c release
ARM64_BIN=$(swift build \
    --package-path "$PROJECT_DIR" \
    --scratch-path "$ARM64_BUILD" \
    --triple arm64-apple-macosx13.0 \
    -c release \
    --show-bin-path)
X86_64_BIN=$(swift build \
    --package-path "$PROJECT_DIR" \
    --scratch-path "$X86_64_BUILD" \
    --triple x86_64-apple-macosx13.0 \
    -c release \
    --show-bin-path)
mkdir -p "$APP_DIR/Contents/MacOS"
lipo -create \
    "$ARM64_BIN/ChargePilotAgent" \
    "$X86_64_BIN/ChargePilotAgent" \
    -output "$APP_DIR/Contents/MacOS/ChargePilotAgent"
cp "$PROJECT_DIR/Info.plist" "$APP_DIR/Contents/Info.plist"
chmod 755 "$APP_DIR/Contents/MacOS/ChargePilotAgent"
cp "$PROJECT_DIR/DMG-README.md" "$STAGING_DIR/README.md"
hdiutil create \
    -volname ChargePilotAgent \
    -srcfolder "$STAGING_DIR" \
    -ov \
    -format UDZO \
    "$OUTPUT_DIR/ChargePilotAgent-$VERSION.dmg"

printf 'Created universal ARM64/Intel DMG: %s\n' "$OUTPUT_DIR/ChargePilotAgent-$VERSION.dmg"
