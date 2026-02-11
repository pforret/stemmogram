# Stemmogram

Audio visualisation tool that splits an MP3 into 4 stems (vocals, bass, drums, other) and composites their color-coded waveforms + spectrograms into a single 1920x1080 PNG.

## Pipeline

1. **Stem separation** — splits audio into 4 stems using `htdemucs` (Facebook's Demucs)
2. **Visualization** — creates a 1920x250 spectrogram, waveform, or combined strip per stem via `ffmpeg`
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
stemmogram /input/song.mp3                        # waveform + spectrogram combined (default)
stemmogram /input/song.mp3 --visual=spectro       # spectrogram only
stemmogram /input/song.mp3 --visual=wave          # waveform only
stemmogram /input/song.mp3 --visual=spectro,wave  # waveform + spectrogram combined
stemmogram /input/song.mp3 --visual=mel           # mel spectrogram (librosa)
stemmogram /input/song.mp3 --scale=lin            # linear scaling (default: log)
stemmogram /input/song.mp3 --colors=ocean         # ocean color palette (default: simple)
stemmogram /input/song.mp3 -o result.png          # custom output filename (in /output)
```

Output files are always written to `/output`. Without `-o`, the filename is auto-generated from the input name and mode (e.g. `song_both.png`, `song_stemmogram.png`, `song_waveform.png`).

## Output

All modes produce a 1920x1080 PNG with an 80px header + 4 × 250px stem strips.

![Example stemmogram](assets/example.png)

### Default (`--visual=spectro,wave`)

Output: `song_both.png`

Each 250px stem strip contains a waveform (120px) + 10px gap + spectrogram (120px), both in the stem's color.

### `--visual=spectro`

Output: `song_stemmogram.png`

- **Header** (80px) — filename, duration, loudness (LUFS), bitrate
- **Vocals** (250px) — red spectrogram
- **Other** (250px) — green spectrogram
- **Bass** (250px) — blue spectrogram
- **Drums** (250px) — orange spectrogram

### `--visual=wave`

Output: `song_waveform.png`

Same layout, but each 250px strip is a waveform instead of a spectrogram.

## Requirements

Only Docker is needed on the host. The container includes Python, PyTorch (CPU), Demucs, ffmpeg, and Pillow.
