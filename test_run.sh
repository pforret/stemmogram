#!/usr/bin/env bash
set -euo pipefail

IMAGE="stemmogram"
INPUT="input/test.mp3"
MODE="${1:-spectrogram}"

usage() {
    echo "Usage: $0 [mode]"
    echo ""
    echo "Modes:"
    echo "  spectrogram     (default) frequency spectrogram"
    echo "  waveform        waveform visualization"
    echo "  both            waveform + spectrogram combined"
    echo "  melspectrogram  mel spectrogram via essentia"
    echo "  all             run all modes"
    exit 1
}

run_mode() {
    local flag=""
    case "$1" in
        spectrogram)    flag="" ;;
        waveform)       flag="--waveform" ;;
        both)           flag="--both" ;;
        melspectrogram) flag="--melspectrogram" ;;
        *)              usage ;;
    esac
    echo "=== Running mode: $1 ==="
    docker run --rm \
        -v "$(pwd)/input:/input" \
        -v "$(pwd)/output:/output" \
        "$IMAGE" /input/test.mp3 $flag
}

# Build
echo "=== Building Docker image ==="
docker build -t "$IMAGE" .

# Run
if [[ "$MODE" == "all" ]]; then
    for m in spectrogram waveform both melspectrogram; do
        run_mode "$m"
    done
elif [[ "$MODE" == "-h" || "$MODE" == "--help" ]]; then
    usage
else
    run_mode "$MODE"
fi

echo "=== Done. Output in ./output/ ==="
ls -lh output/*.png 2>/dev/null || true
