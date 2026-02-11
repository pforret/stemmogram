#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-stemmogram}"
INPUT="${INPUT:-/input/test.mp3}"

VISUALS=("spectro" "wave" "spectro,wave" "mel")
SCALES=("lin" "log")
COLORS=("simple" "ocean")

# Build
echo "=== Building Docker image ==="
docker build -t "$IMAGE" .

# Run all combinations
for visual in "${VISUALS[@]}"; do
  for scale in "${SCALES[@]}"; do
    for color in "${COLORS[@]}"; do
      # Create output filename from options
      visual_slug="${visual//,/-}"
      output="test_${visual_slug}_${scale}_${color}.png"

      echo "=== Running: visual=$visual scale=$scale colors=$color ==="
      docker run --rm \
        -v "$(pwd)/input:/input" \
        -v "$(pwd)/output:/output" \
        "$IMAGE" "$INPUT" \
        --visual="$visual" \
        --scale="$scale" \
        --colors="$color" \
        --output="$output"
    done
  done
done

echo "=== Done! Generated 16 variants ==="
