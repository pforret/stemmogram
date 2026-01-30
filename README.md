# Stemmogram

Audio visualization tool that splits an MP3 into 4 stems (vocals, bass, drums, other) and composites their color-coded spectrograms into a single 1920x1080 PNG.

## Pipeline

1. **Stem separation** — splits audio into 4 stems using `htdemucs` (Facebook's Demucs)
2. **Spectrogram generation** — creates a 1920x250 spectrogram per stem via `ffmpeg`
3. **Color tinting** — each stem gets a distinct color: vocals=yellow, bass=blue, drums=red, other=green
4. **Compositing** — stacks a metadata header (80px) + 4 spectrograms (4x250px) = 1920x1080

## Build

```bash
docker build -t stemmogram .
```

## Usage

```bash
mkdir -p input output
cp /path/to/song.mp3 input/

docker run --rm \
  -v "$(pwd)/input:/input" \
  -v "$(pwd)/output:/output" \
  stemmogram /input/song.mp3
```

The output PNG appears in `./output/song_stemmogram.png`.

### Options

```
stemmogram /input/song.mp3              # output to /output (default)
stemmogram /input/song.mp3 -o /output   # explicit output directory
```

## Output

A 1920x1080 PNG with:
- **Header** (80px) — filename, duration, loudness (LUFS), bitrate
- **Vocals** (250px) — yellow spectrogram
- **Bass** (250px) — blue spectrogram
- **Drums** (250px) — red spectrogram
- **Other** (250px) — green spectrogram

## Requirements

Only Docker is needed on the host. The container includes Python, PyTorch (CPU), Demucs, ffmpeg, and Pillow.
