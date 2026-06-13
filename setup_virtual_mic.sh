#!/bin/bash
# DroidMic — Linux Virtual Microphone Setup
# Creates a PulseAudio/PipeWire null sink that acts as a virtual microphone.
#
# Usage:
#   ./setup_virtual_mic.sh          # Create the virtual mic
#   ./setup_virtual_mic.sh --remove # Remove the virtual mic
#
# After running this script, select "DroidMic Microphone" as your input
# device in Discord, Zoom, OBS, or your system sound settings.

set -euo pipefail

SINK_NAME="DroidMic"
SOURCE_NAME="DroidMicInput"
SINK_DESC="DroidMic"
SOURCE_DESC="DroidMic_Microphone"
RATE=44100
CHANNELS=1

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Check for pactl
if ! command -v pactl &> /dev/null; then
    error "pactl not found. Install PulseAudio or PipeWire:"
    echo "  Ubuntu/Debian:  sudo apt install pulseaudio-utils"
    echo "  Arch Linux:     sudo pacman -S libpulse"
    echo "  Fedora:         sudo dnf install pulseaudio-utils"
    exit 1
fi

remove_virtual_mic() {
    info "Removing DroidMic virtual devices..."

    # Find and unload DroidMic modules
    local found=false
    while IFS=$'\t' read -r idx name args 2>/dev/null; do
        if [[ "$args" == *"$SINK_NAME"* ]]; then
            pactl unload-module "$idx" 2>/dev/null && \
                info "Unloaded module $idx ($name)" || true
            found=true
        fi
    done < <(pactl list modules short 2>/dev/null)

    if [ "$found" = false ]; then
        warn "No DroidMic modules found."
    else
        info "DroidMic virtual devices removed."
    fi
}

create_virtual_mic() {
    # Remove existing first to avoid duplicates
    remove_virtual_mic

    info "Creating DroidMic virtual microphone..."

    # Create null sink (virtual speaker)
    SINK_ID=$(pactl load-module module-null-sink \
        sink_name="$SINK_NAME" \
        sink_properties=device.description="$SINK_DESC" \
        rate="$RATE" \
        channels="$CHANNELS" \
        format=s16le)
    info "Created null sink '$SINK_NAME' (module $SINK_ID)"

    # Remap the sink's monitor as a source (virtual microphone)
    SOURCE_ID=$(pactl load-module module-remap-source \
        master="${SINK_NAME}.monitor" \
        source_name="$SOURCE_NAME" \
        source_properties=device.description="$SOURCE_DESC")
    info "Created virtual microphone '$SOURCE_NAME' (module $SOURCE_ID)"

    echo ""
    info "Virtual microphone ready!"
    info "Select '${SOURCE_DESC}' as your microphone in application settings."
    echo ""
    echo "  To remove:  $0 --remove"
    echo ""
}

# Parse arguments
case "${1:-}" in
    --remove|-r)
        remove_virtual_mic
        ;;
    --help|-h)
        echo "Usage: $0 [--remove|--help]"
        echo ""
        echo "  (no args)   Create the DroidMic virtual microphone"
        echo "  --remove    Remove the DroidMic virtual microphone"
        echo "  --help      Show this help"
        ;;
    *)
        create_virtual_mic
        ;;
esac
