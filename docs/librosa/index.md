# Librosa — Alternative Mel Spectrogram

[Librosa](https://librosa.org/) is a widely-used Python library for audio analysis. It could replace [Essentia](https://essentia.upf.edu/) for mel spectrogram generation in stemmogram's `--melspectrogram` mode.

## What it does

Librosa provides audio loading, feature extraction (MFCCs, mel spectrograms, chroma, tempo), and display utilities. For stemmogram, the relevant function is `librosa.feature.melspectrogram`.

## Current implementation (Essentia)

From `stemmogram.py:199-236`:

```python
from essentia.standard import (
    FrameGenerator, MelBands, MonoLoader, Spectrum, UnaryOperator, Windowing,
)

audio = MonoLoader(filename=wav_path, sampleRate=44100)()
w = Windowing(type='hann')
spectrum = Spectrum()
mel = MelBands(numberBands=128, sampleRate=44100, inputSize=1025,
               lowFrequencyBound=20, highFrequencyBound=20000, log=False)
log_norm = UnaryOperator(type='log')

mel_bands = []
for frame in FrameGenerator(audio, frameSize=2048, hopSize=512, startFromZero=True):
    mb = mel(spectrum(w(frame)))
    mel_bands.append(log_norm(mb))

mel_array = np.array(mel_bands)
# ... normalize to 0-255, flip, resize, save
```

## Librosa equivalent

```python
import librosa
import numpy as np
from PIL import Image

def generate_melspectrogram(wav_path: str, output_png: str, height: int = 250):
    y, sr = librosa.load(wav_path, sr=44100, mono=True)
    mel = librosa.feature.melspectrogram(
        y=y, sr=sr,
        n_mels=128,
        n_fft=2048,
        hop_length=512,
        fmin=20,
        fmax=20000,
        window='hann',
    )
    mel_db = librosa.power_to_db(mel, ref=np.max)

    # Normalize to 0-255
    mel_norm = ((mel_db - mel_db.min()) / (mel_db.max() - mel_db.min()) * 255)
    mel_img = np.flipud(mel_norm).astype(np.uint8)

    img = Image.fromarray(mel_img, mode='L')
    img = img.resize((1920, height), Image.LANCZOS)
    img.save(output_png)
```

### Parameter mapping

| Purpose | Essentia | Librosa |
|---------|----------|---------|
| Load audio | `MonoLoader(filename, sampleRate=44100)` | `librosa.load(path, sr=44100, mono=True)` |
| FFT size | `frameSize=2048` → `inputSize=1025` | `n_fft=2048` |
| Hop size | `hopSize=512` | `hop_length=512` |
| Mel bands | `numberBands=128` | `n_mels=128` |
| Frequency range | `lowFrequencyBound=20, highFrequencyBound=20000` | `fmin=20, fmax=20000` |
| Window | `Windowing(type='hann')` | `window='hann'` |
| Log scale | `UnaryOperator(type='log')` | `librosa.power_to_db()` |

## Comparison

| | Essentia | Librosa |
|---|---|---|
| **Developer** | Music Technology Group (UPF) | Librosa team |
| **Focus** | Music information retrieval | General audio analysis |
| **Dependencies** | C++ core + Python bindings | Pure Python + NumPy/SciPy |
| **Install size** | ~200 MB (includes C++ libs) | ~30 MB |
| **Docker image impact** | Requires C++ build tools | Minimal, pip-only |
| **Install difficulty** | Can be tricky (binary wheels not always available) | `pip install librosa` — just works |
| **API style** | Frame-by-frame processing loop | Single function call |
| **dB conversion** | Manual via `UnaryOperator` | Built-in `power_to_db()` |
| **Output quality** | Equivalent | Equivalent |
| **License** | AGPL-3.0 | ISC (permissive) |

## Why librosa may be preferred

- **Simpler code** — single function call vs. manual frame loop (6 lines vs. 15)
- **Easier install** — pure Python, no C++ compilation issues in Docker
- **Smaller image** — ~170 MB less in the Docker container
- **Permissive license** — ISC vs. Essentia's AGPL-3.0
- **Better documented** — extensive tutorials and examples

## Code change required

In `stemmogram.py`, replace the `generate_melspectrogram` function (line 199) and swap the import:

```python
# Remove
from essentia.standard import (
    FrameGenerator, MelBands, MonoLoader, Spectrum, UnaryOperator, Windowing,
)

# Add
import librosa
```

The rest of the pipeline (tinting, compositing) stays unchanged since the output is the same: a grayscale PNG.

## Installation

```bash
pip install librosa
```

Requires Python 3.8+ and NumPy/SciPy (installed automatically).

## References

- [Librosa documentation](https://librosa.org/doc/)
- [librosa.feature.melspectrogram](https://librosa.org/doc/latest/generated/librosa.feature.melspectrogram.html)
- [Mel spectrogram tutorial](https://librosa.org/doc/latest/tutorial.html)
