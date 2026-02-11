# Demucs — Stem Separation

[Demucs](https://github.com/facebookresearch/demucs) is Facebook Research's deep-learning model for music source separation. Stemmogram uses the **htdemucs** variant (Hybrid Transformer Demucs).

## What it does

Splits a single audio file into 4 stems:

| Stem | Description |
|------|-------------|
| `vocals` | Singing, speech |
| `bass` | Bass guitar, sub-bass |
| `drums` | Percussion, kicks, snares |
| `other` | Everything else (guitar, synth, keys) |

## How stemmogram uses it

```bash
python3 -m demucs -n htdemucs --out <output_dir> <input.mp3>
```

Output structure:

```
<output_dir>/htdemucs/<track_name>/
    vocals.wav
    bass.wav
    drums.wav
    other.wav
```

All outputs are 44.1 kHz stereo WAV files, regardless of the input format.

## Key flags

| Flag | Purpose |
|------|---------|
| `-n htdemucs` | Select the Hybrid Transformer model (best quality/speed tradeoff) |
| `--out <dir>` | Output directory for separated stems |

## Available models

| Model | Notes |
|-------|-------|
| `htdemucs` | Default. Hybrid Transformer, 4 stems. Used by stemmogram. |
| `htdemucs_ft` | Fine-tuned variant. Better quality, slower. |
| `htdemucs_6s` | 6 stems (adds piano and guitar). |
| `mdx_extra` | Older architecture, still decent quality. |

## Performance

- Requires PyTorch (CPU or CUDA)
- A 4-minute song takes ~2-4 min on CPU, ~30s on GPU
- Memory: ~4 GB RAM minimum, more for longer tracks
- The model weights (~80 MB) are downloaded on first run and cached

## Installation

Installed inside the Docker container via pip:

```bash
pip install demucs
```

Requires Python 3.8+ and PyTorch.

## References

- [Demucs GitHub](https://github.com/facebookresearch/demucs)
- [Hybrid Transformer paper](https://arxiv.org/abs/2211.08553) (Rouard, Massa, Défossez, 2023)
