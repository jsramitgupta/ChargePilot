#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUTPUT_DIR="$PROJECT_DIR/dist"
STAGING_DIR="$OUTPUT_DIR/staging"
VERSION=0.1.0
ARM64_BUILD="$PROJECT_DIR/.build/dmg-arm64"
X86_64_BUILD="$PROJECT_DIR/.build/dmg-x86_64"

mkdir -p "$STAGING_DIR"
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
lipo -create \
    "$ARM64_BUILD/out/Products/Release/ChargePilotAgent" \
    "$X86_64_BUILD/out/Products/Release/ChargePilotAgent" \
    -output "$STAGING_DIR/ChargePilotAgent"
chmod 755 "$STAGING_DIR/ChargePilotAgent"
cp "$PROJECT_DIR/DMG-README.md" "$STAGING_DIR/README.md"
hdiutil create \
    -volname ChargePilotAgent \
    -srcfolder "$STAGING_DIR" \
    -ov \
    -format UDZO \
    "$OUTPUT_DIR/ChargePilotAgent-$VERSION.dmg"

printf 'Created universal ARM64/Intel DMG: %s\n' "$OUTPUT_DIR/ChargePilotAgent-$VERSION.dmg"
