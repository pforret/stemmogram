# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Stemmogram is a Dockerized audio visualization tool. It takes an MP3 file as input and produces a 1920x1080 PNG "stemmogram" image as output.

### Pipeline

1. **Stem separation** — split MP3 into 4 stems (vocals, bass, drums, other) using `htdemucs` (from the `demucs` package)
2. **Visualization** — create 1920x250 spectrogram/waveform/both per stem using `ffmpeg` (configurable via `--visual`)
3. **Color mapping** — each stem gets a distinct color: vocals=red, bass=blue, drums=orange, other=green
4. **Compositing** — stack the 4 strips vertically (1920x1000), then add a 1920x80 header bar showing filename, duration, loudness, and bitrate
5. **Output** — final 1920x1080 PNG stemmogram

## Architecture

The entire program runs inside a Docker container. Key dependencies:

- **demucs / htdemucs** — Facebook's music source separation model (Python/PyTorch)
- **ffmpeg** — spectrogram rendering via the `showspectrumpic` filter
- **ImageMagick or Pillow** — image compositing and text rendering

### File Layout

```
Dockerfile          # Builds the container with demucs, ffmpeg, Python deps
entrypoint.sh       # Main script orchestrating the pipeline
input/              # Mount point for input MP3 files
output/             # Mount point for output PNG files
```

## Build and Run

```bash
# Build the Docker image
docker build -t stemmogram .

# Process a single MP3 file
docker run --rm -v "$(pwd)/input:/input" -v "$(pwd)/output:/output" stemmogram /input/song.mp3

# The output PNG will appear in ./output/
```

## Key Technical Details

- **htdemucs** outputs 4 WAV files: `vocals.wav`, `bass.wav`, `drums.wav`, `other.wav`
- **ffmpeg spectrogram**: `ffmpeg -i stem.wav -lavfi showspectrumpic=s=1920x250:scale=log output.png`
- **ffmpeg waveform**: `ffmpeg -i stem.wav -lavfi showwavespic=s=1920x250:scale=log output.png`
- **Options**: `--visual=spectro,wave` (default), `spectro`, `wave`, `mel`; `--scale=log` (default) or `lin`
- Color tinting is applied per-stem after visualization generation
- The header bar uses audio metadata extracted via `ffprobe` (duration, bitrate) and `ffmpeg` loudness scanning (`ebur128`)
- Final image dimensions: 1920x1080 (80px header + 4x250px strips)

## Design Constraints

- All processing happens in Docker — no host dependencies beyond Docker itself
- The container must include PyTorch (for demucs), ffmpeg, and image manipulation tools
- Input/output directories are bind-mounted volumes
- The pipeline is sequential: stem separation must complete before spectrogram generation
