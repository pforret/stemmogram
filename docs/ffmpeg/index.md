# FFmpeg — Spectrogram, Waveform & Metadata

[FFmpeg](https://ffmpeg.org/) handles three roles in stemmogram: spectrogram rendering, waveform rendering, and audio metadata extraction.

## Spectrogram generation

Uses the `showspectrumpic` filter to render a frequency-vs-time image from a WAV stem.

```bash
ffmpeg -y -i stem.wav \
  -lavfi "showspectrumpic=s=1920x250:legend=0:start=18:stop=18000:win_func=hann:scale=log:fscale=log" \
  output.png
```

### Parameters

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `s` | `1920x250` | Output image size (full width, per-stem height) |
| `legend` | `0` | Disable built-in legend (stemmogram adds its own labels) |
| `start` | `18` | Low frequency cutoff (Hz) — skip sub-bass rumble |
| `stop` | `18000` | High frequency cutoff (Hz) — skip inaudible range |
| `win_func` | `hann` | Windowing function for FFT |
| `scale` | `log` | Logarithmic amplitude scale (better dynamic range visibility) |
| `fscale` | `log` | Logarithmic frequency axis (matches human hearing) |

The output is a grayscale PNG that gets color-tinted per stem by Pillow.

## Waveform generation

Uses the `showwavespic` filter to render an amplitude-vs-time image.

```bash
ffmpeg -y -i stem.wav \
  -lavfi "showwavespic=s=1920x250:colors=white:scale=log" \
  output.png
```

### Parameters

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `s` | `1920x250` | Output image size |
| `colors` | `white` | Waveform drawn in white (tinted later by Pillow) |
| `scale` | `log` | Logarithmic amplitude scale |

## Metadata extraction

### ffprobe — duration, bitrate, sample rate

```bash
ffprobe -v quiet -print_format json -show_format -show_streams input.mp3
```

Extracts from the JSON output:

- `format.duration` — total duration in seconds
- `format.bit_rate` — bitrate in bps
- `streams[0].sample_rate` — audio sample rate

### ebur128 — integrated loudness (LUFS)

```bash
ffmpeg -i input.mp3 -af ebur128=framelog=verbose -f null -
```

Parses stderr for `I: -14.0 LUFS` (integrated loudness per EBU R128 standard).

### volumedetect — mean and peak volume

```bash
ffmpeg -i input.mp3 -af volumedetect -f null -
```

Parses stderr for:

- `mean_volume: -16.0 dB`
- `max_volume: -0.3 dB`

## All ffmpeg commands used

| Purpose | Filter/Tool | Output |
|---------|-------------|--------|
| Spectrogram | `showspectrumpic` | PNG image |
| Waveform | `showwavespic` | PNG image |
| Duration/bitrate | `ffprobe` | JSON metadata |
| Loudness (LUFS) | `ebur128` | stderr text |
| Volume (dB) | `volumedetect` | stderr text |

## References

- [showspectrumpic filter](https://ffmpeg.org/ffmpeg-filters.html#showspectrumpic)
- [showwavespic filter](https://ffmpeg.org/ffmpeg-filters.html#showwavespic)
- [ebur128 filter](https://ffmpeg.org/ffmpeg-filters.html#ebur128-1)
- [volumedetect filter](https://ffmpeg.org/ffmpeg-filters.html#volumedetect)
- [ffprobe documentation](https://ffmpeg.org/ffprobe.html)
