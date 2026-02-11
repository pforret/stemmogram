# Spleeter — Alternative Stem Separation

[Spleeter](https://github.com/deezer/spleeter) is Deezer's open-source library for music source separation. It could replace Demucs in the stemmogram pipeline.

## What it does

Same goal as Demucs: splits audio into stems using a pre-trained neural network (U-Net architecture with TensorFlow).

Available pre-trained models:

| Model | Stems |
|-------|-------|
| `spleeter:2stems` | vocals, accompaniment |
| `spleeter:4stems` | vocals, bass, drums, other |
| `spleeter:5stems` | vocals, bass, drums, piano, other |

The **4stems** model matches stemmogram's current pipeline exactly.

## Equivalent command

Current (Demucs):

```bash
python3 -m demucs -n htdemucs --out <output_dir> <input.mp3>
# output: <output_dir>/htdemucs/<track>/vocals.wav, bass.wav, drums.wav, other.wav
```

Spleeter equivalent:

```bash
spleeter separate -p spleeter:4stems -o <output_dir> <input.mp3>
# output: <output_dir>/<track>/vocals.wav, bass.wav, drums.wav, other.wav
```

### Key difference in output paths

| | Path pattern |
|---|---|
| Demucs | `<out>/htdemucs/<track>/<stem>.wav` |
| Spleeter | `<out>/<track>/<stem>.wav` |

The `separate_stems()` function in `stemmogram.py` would need its path construction adjusted (line 156).

## Code change required

In `stemmogram.py`, the `separate_stems()` function would change:

```python
# Current (demucs)
subprocess.run([
    "python3", "-m", "demucs",
    "-n", "htdemucs",
    "--out", sep_dir,
    input_path,
], check=True)
stem_dir = os.path.join(sep_dir, "htdemucs", track_name)

# Spleeter equivalent
subprocess.run([
    "spleeter", "separate",
    "-p", "spleeter:4stems",
    "-o", sep_dir,
    input_path,
], check=True)
stem_dir = os.path.join(sep_dir, track_name)
```

## Comparison

| | Demucs (htdemucs) | Spleeter (4stems) |
|---|---|---|
| **Developer** | Meta / Facebook Research | Deezer |
| **Architecture** | Hybrid Transformer | U-Net (CNN) |
| **ML framework** | PyTorch | TensorFlow |
| **Separation quality** | Better (state-of-the-art) | Good, but audible artifacts |
| **Speed (CPU, 4-min song)** | ~2-4 min | ~1-2 min |
| **Model size** | ~80 MB | ~50 MB per model |
| **Docker image impact** | PyTorch (~1.5 GB) | TensorFlow (~1.2 GB) |
| **Output format** | WAV (44.1 kHz) | WAV (44.1 kHz) |
| **Stem names** | vocals, bass, drums, other | vocals, bass, drums, other |
| **Python API** | `demucs.separate` | `spleeter.separator.Separator` |
| **Last major update** | 2023 | 2022 |
| **License** | MIT | MIT |

## Why stemmogram uses Demucs

Demucs produces noticeably cleaner separation, especially on vocals and drums. Spleeter is faster but introduces more bleeding between stems, which shows up as ghost patterns in the spectrograms.

## When Spleeter might be preferred

- Faster processing is more important than quality
- TensorFlow is already in the stack
- Smaller Docker image is needed
- Running on constrained hardware (lower memory usage)

## Installation

```bash
pip install spleeter
```

Requires Python 3.8+ and TensorFlow 2.x. Model weights are downloaded on first run.

## References

- [Spleeter GitHub](https://github.com/deezer/spleeter)
- [Spleeter paper](https://archives.ismir.net/ismir2020/latebreaking/000008.pdf) (Hennequin et al., 2020)
- [Demucs vs Spleeter comparison](https://github.com/facebookresearch/demucs#comparison-with-other-models)
