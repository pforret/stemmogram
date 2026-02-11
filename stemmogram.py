#!/usr/bin/env python3
"""Stemmogram: audio visualization via stem separation and spectrograms."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

STEMS = ["vocals", "other", "bass", "drums"]
COLOR_PALETTES = {
    "simple": {
        "vocals": (207, 46, 46),
        "bass": (30, 80, 180),
        "drums": (180, 120, 0),
        "other": (0, 145, 110),
    },
    "ocean": {
        "vocals": (213, 137, 111),  # d5896f
        "bass": (4, 57, 94),        # 04395e
        "drums": (218, 183, 133),   # dab785
        "other": (112, 162, 136),   # 70a288
    },
}
WIDTH = 1920
SPEC_HEIGHT = 250
HEADER_HEIGHT = 80
TOTAL_HEIGHT = HEADER_HEIGHT + len(STEMS) * SPEC_HEIGHT  # 1080
BOTH_STRIP_HEIGHT = 120
BOTH_GAP = 10


def parse_args():
    parser = argparse.ArgumentParser(description="Generate a stemmogram from an MP3 file.")
    parser.add_argument("input", help="Path to input MP3 file")
    parser.add_argument(
        "--output", "-o", default=None, help="Output filename (placed in /output)"
    )
    parser.add_argument(
        "--visual", default="spectro,wave",
        help="Visualization mode: spectro, wave, spectro,wave, or mel (default: spectro,wave)"
    )
    parser.add_argument(
        "--scale", default="log", choices=["lin", "log", "sqrt", "cbrt"],
        help="Scaling method for waveform/spectrogram: lin, log, sqrt, or cbrt (default: log)"
    )
    parser.add_argument(
        "--colors", default="simple", choices=list(COLOR_PALETTES.keys()),
        help="Color palette: simple or ocean (default: simple)"
    )
    parser.add_argument(
        "--cache", default=None,
        help="Unique ID for caching stems (reuses stems if already separated)"
    )
    return parser.parse_args()


def extract_metadata(input_path: str) -> dict:
    """Extract duration, bitrate via ffprobe and loudness via ffmpeg ebur128."""
    # Duration, bitrate, and sample rate
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            input_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(result.stdout)
    fmt = info.get("format", {})
    duration_s = float(fmt.get("duration", 0))
    bitrate_bps = int(fmt.get("bit_rate", 0))

    # Sample rate from first audio stream
    sample_rate = "N/A"
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "audio":
            sr = stream.get("sample_rate")
            if sr:
                sample_rate = f"{int(sr) // 1000}kHz" if int(sr) >= 1000 else f"{sr}Hz"
            break

    minutes = int(duration_s // 60)
    seconds = int(duration_s % 60)
    duration_str = f"{minutes}:{seconds:02d}"
    bitrate_kbps = bitrate_bps // 1000

    # Integrated loudness (LUFS) via ebur128
    lufs_value = None
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-i", input_path,
                "-af", "ebur128=framelog=verbose",
                "-f", "null",
                "-",
            ],
            capture_output=True,
            text=True,
        )
        stderr = result.stderr
        match = re.search(r"I:\s+([-\d.]+)\s+LUFS", stderr)
        if match:
            lufs_value = float(match.group(1))
    except Exception:
        pass

    # Mean and max volume via volumedetect
    mean_volume = "N/A"
    max_volume = "N/A"
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-i", input_path,
                "-af", "volumedetect",
                "-f", "null",
                "-",
            ],
            capture_output=True,
            text=True,
        )
        stderr = result.stderr
        match_mean = re.search(r"mean_volume:\s+([-\d.]+)\s+dB", stderr)
        match_max = re.search(r"max_volume:\s+([-\d.]+)\s+dB", stderr)
        if match_mean:
            mean_volume = f"{float(match_mean.group(1)):.1f} dB"
        if match_max:
            max_volume = f"{float(match_max.group(1)):.1f} dB"
    except Exception:
        pass

    return {
        "duration": duration_str,
        "duration_s": duration_s,
        "bitrate_kbps": bitrate_kbps,
        "lufs": lufs_value,
        "sample_rate": sample_rate,
        "mean_volume": mean_volume,
        "max_volume": max_volume,
    }


def separate_stems(input_path: str, tmp_dir: str, cache_id: str = None) -> dict:
    """Run demucs htdemucs to separate audio into stems. Returns dict of stem name -> wav path."""
    cache_dir = "/cache"

    # Check if cached stems exist
    if cache_id:
        cached_stem_dir = os.path.join(cache_dir, cache_id)
        cached_paths = {stem: os.path.join(cached_stem_dir, f"{stem}.wav") for stem in STEMS}
        if all(os.path.isfile(p) for p in cached_paths.values()):
            print(f"  Using cached stems from: {cached_stem_dir}")
            return cached_paths

    # Run demucs separation
    sep_dir = os.path.join(tmp_dir, "separated")
    subprocess.run(
        [
            "python3", "-m", "demucs",
            "-n", "htdemucs",
            "--out", sep_dir,
            input_path,
        ],
        check=True,
    )

    # demucs outputs to <sep_dir>/htdemucs/<track_name>/<stem>.wav
    track_name = Path(input_path).stem
    stem_dir = os.path.join(sep_dir, "htdemucs", track_name)

    stem_paths = {}
    for stem in STEMS:
        wav_path = os.path.join(stem_dir, f"{stem}.wav")
        if not os.path.isfile(wav_path):
            print(f"ERROR: Expected stem file not found: {wav_path}", file=sys.stderr)
            sys.exit(1)
        stem_paths[stem] = wav_path

    # Save to cache if cache_id provided
    if cache_id:
        import shutil
        cached_stem_dir = os.path.join(cache_dir, cache_id)
        os.makedirs(cached_stem_dir, exist_ok=True)
        for stem, src_path in stem_paths.items():
            dst_path = os.path.join(cached_stem_dir, f"{stem}.wav")
            shutil.copy2(src_path, dst_path)
            stem_paths[stem] = dst_path
        print(f"  Cached stems to: {cached_stem_dir}")

    return stem_paths


def generate_spectrogram(wav_path: str, output_png: str, height: int = SPEC_HEIGHT, scale: str = "log"):
    """Generate a spectrogram PNG using ffmpeg showspectrumpic."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", wav_path,
            "-lavfi", f"showspectrumpic=s={WIDTH}x{height}:legend=0:start=18:stop=18000:win_func=hann:scale={scale}:fscale=log",
            output_png,
        ],
        capture_output=True,
        check=True,
    )


def generate_waveform(wav_path: str, output_png: str, height: int = SPEC_HEIGHT, scale: str = "log"):
    """Generate a waveform PNG using ffmpeg showwavespic."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", wav_path,
            "-lavfi", f"showwavespic=s={WIDTH}x{height}:colors=white:scale={scale}",
            output_png,
        ],
        capture_output=True,
        check=True,
    )


def generate_melspectrogram(wav_path: str, output_png: str, height: int = SPEC_HEIGHT):
    """Generate a mel spectrogram PNG using librosa."""
    import librosa

    y, sr = librosa.load(wav_path, sr=44100)
    S = librosa.feature.melspectrogram(
        y=y, sr=sr, n_mels=128, n_fft=2048, hop_length=512, fmin=20, fmax=20000,
    )
    S_dB = librosa.power_to_db(S, ref=np.max)

    # Normalize to 0-255 (S_dB ranges from ~-80 to 0)
    s_min, s_max = S_dB.min(), S_dB.max()
    if s_max > s_min:
        mel_norm = (S_dB - s_min) / (s_max - s_min) * 255
    else:
        mel_norm = np.zeros_like(S_dB)

    # Flip vertically so low frequencies are at the bottom
    mel_img = np.flipud(mel_norm).astype(np.uint8)

    img = Image.fromarray(mel_img, mode='L')
    img = img.resize((WIDTH, height), Image.LANCZOS)
    img.save(output_png)


def tint_spectrogram(png_path: str, color: tuple, height: int = SPEC_HEIGHT) -> Image.Image:
    """Load a spectrogram, invert to white background, and tint with the given RGB color."""
    img = Image.open(png_path).convert("L")  # grayscale
    img = img.resize((WIDTH, height), Image.LANCZOS)
    img = ImageOps.invert(img)  # black-on-white: silence=255, loud=0

    # Map: 0 (loud) -> stem color, 255 (silence) -> white
    r_channel = img.point(lambda p: int(color[0] + p * (255 - color[0]) / 255))
    g_channel = img.point(lambda p: int(color[1] + p * (255 - color[1]) / 255))
    b_channel = img.point(lambda p: int(color[2] + p * (255 - color[2]) / 255))

    return Image.merge("RGB", (r_channel, g_channel, b_channel))


def combine_stem_strips(wave_img: Image.Image, spec_img: Image.Image) -> Image.Image:
    """Stack a waveform and spectrogram strip with a gap into a SPEC_HEIGHT-tall image."""
    combined = Image.new("RGB", (WIDTH, SPEC_HEIGHT), "white")
    combined.paste(wave_img, (0, 0))
    combined.paste(spec_img, (0, BOTH_STRIP_HEIGHT + BOTH_GAP))
    return combined


def create_lufs_meter(lufs_value: float, width: int = 200, height: int = 28, segments: int = 10) -> Image.Image:
    """
    Create LED-style LUFS meter visualization.
    Range: -30 to 0 LUFS (3 LUFS per segment, 10 segments total)

    LUFS color zones:
      > -9   : red (too loud/clipped)
      -9 to -12: orange (loud)
      -12 to -18: green (ok)
      < -18  : dark green (quiet)
    """
    img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    # Range: -30 to 0 LUFS, 3 LUFS per segment
    clamped = max(-30, min(0, lufs_value))
    lit_segments = int((clamped + 30) / 3)

    gap = 2
    seg_width = (width - (segments - 1) * gap) // segments

    for i in range(segments):
        x = i * (seg_width + gap)
        # Each segment represents 3 LUFS: seg 0 = -30 to -27, seg 9 = -3 to 0
        seg_lufs = -30 + (i + 1) * 3  # upper bound of this segment

        if seg_lufs > -9:            # > -9 LUFS zone
            color = (220, 50, 50)     # red
        elif seg_lufs > -12:         # -9 to -12 LUFS zone
            color = (255, 165, 0)     # orange
        elif seg_lufs > -18:         # -12 to -18 LUFS zone
            color = (50, 200, 50)     # green
        else:
            color = (30, 120, 30)     # dark green

        if i < lit_segments:
            draw.rectangle([x, 0, x + seg_width - 1, height - 1], fill=color + (255,))
        else:
            # Unlit segments: same color but 90% transparent
            draw.rectangle([x, 0, x + seg_width - 1, height - 1], fill=color + (25,))

    return img


def create_header(filename: str, metadata: dict) -> Image.Image:
    """Create an 1920x80 header bar with metadata text."""
    header = Image.new("RGB", (WIDTH, HEADER_HEIGHT), "white")
    draw = ImageDraw.Draw(header)

    # Try to load DejaVu Sans, fall back to default
    font_size = 28
    label_size = 20
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", label_size)
    except OSError:
        font = ImageFont.load_default()
        label_font = font

    # Layout: filename on the left, stats on the right
    name = Path(filename).stem
    draw.text((20, 10), name, fill="black", font=font)

    stats = (
        f"Duration: {metadata['duration']}    "
        f"Bitrate: {metadata['bitrate_kbps']} kbps    "
        f"Sample rate: {metadata['sample_rate']}    "
        f"Mean vol: {metadata['mean_volume']}    "
        f"Max vol: {metadata['max_volume']}"
    )
    draw.text((20, 46), stats, fill="gray", font=label_font)

    # Project reference in top-right corner
    ref_size = 14
    try:
        ref_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", ref_size)
    except OSError:
        ref_font = ImageFont.load_default()
    ref_text = "pforret/stemmogram"
    ref_bbox = draw.textbbox((0, 0), ref_text, font=ref_font)
    ref_w = ref_bbox[2] - ref_bbox[0]
    draw.text((WIDTH - ref_w - 20, 10), ref_text, fill="gray", font=ref_font)

    # LUFS meter below project name
    lufs = metadata.get("lufs")
    if lufs is not None:
        meter_width = 160
        meter_height = 28
        meter_img = create_lufs_meter(lufs, meter_width, meter_height)
        meter_x = WIDTH - meter_width - 20
        meter_y = 28
        header.paste(meter_img, (meter_x, meter_y), meter_img)
        # LUFS value text to the left of meter
        lufs_text = f"{lufs:.1f} LUFS"
        try:
            lufs_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        except OSError:
            lufs_font = label_font
        lufs_bbox = draw.textbbox((0, 0), lufs_text, font=lufs_font)
        lufs_w = lufs_bbox[2] - lufs_bbox[0]
        draw.text((meter_x - lufs_w - 10, meter_y + 4), lufs_text, fill="gray", font=lufs_font)

    return header


def compose_stemmogram(header: Image.Image, spectrograms: list, duration_s: float) -> Image.Image:
    """Stack header + 4 spectrograms into a 1920x1080 image."""
    final = Image.new("RGB", (WIDTH, TOTAL_HEIGHT), "white")
    final.paste(header, (0, 0))

    try:
        label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        time_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except OSError:
        label_font = ImageFont.load_default()
        time_font = label_font

    draw = ImageDraw.Draw(final)
    for i, spec in enumerate(spectrograms):
        y = HEADER_HEIGHT + i * SPEC_HEIGHT
        final.paste(spec, (0, y))
        # White shadow for readability over dark waveforms
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    draw.text((10 + dx, y + 6 + dy), STEMS[i], fill="white", font=label_font)
        draw.text((10, y + 6), STEMS[i], fill="black", font=label_font)

    # Draw semi-transparent time markers every 30 seconds
    if duration_s > 0:
        overlay = Image.new("RGBA", (WIDTH, TOTAL_HEIGHT), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        t = 30
        while t < duration_s:
            x = int(t / duration_s * WIDTH)
            overlay_draw.line([(x, HEADER_HEIGHT), (x, TOTAL_HEIGHT)], fill=(0, 0, 0, 64), width=1)
            minutes = int(t // 60)
            seconds = int(t % 60)
            label = f"{minutes}:{seconds:02d}"
            overlay_draw.text((x - 30, TOTAL_HEIGHT - 18), label, fill=(0, 0, 0, 128), font=time_font)
            t += 30
        final = Image.alpha_composite(final.convert("RGBA"), overlay).convert("RGB")

    return final


def main():
    args = parse_args()
    input_path = args.input
    output_dir = "/output"

    if not os.path.isfile(input_path):
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    print(f"Processing: {input_path}")

    # Step 1: Extract metadata
    print("Extracting metadata...")
    metadata = extract_metadata(input_path)
    lufs_str = f"{metadata['lufs']:.1f} LUFS" if metadata['lufs'] is not None else "N/A"
    print(f"  Duration: {metadata['duration']}, Bitrate: {metadata['bitrate_kbps']} kbps, Loudness: {lufs_str}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Step 2: Separate stems
        print("Separating stems with htdemucs...")
        stem_paths = separate_stems(input_path, tmp_dir, args.cache)

        # Step 3: Generate and tint spectrograms/waveforms
        tinted = []
        visual = args.visual.lower()
        if visual == "spectro,wave" or visual == "wave,spectro":
            mode = "both"
        elif visual == "wave":
            mode = "waveform"
        elif visual == "mel":
            mode = "melspectrogram"
        else:
            mode = "spectrogram"
        palette = COLOR_PALETTES[args.colors]
        for stem in STEMS:
            print(f"  Generating {mode}: {stem}...")
            color = palette[stem]
            if mode == "both":
                wave_png = os.path.join(tmp_dir, f"{stem}_wave.png")
                spec_png = os.path.join(tmp_dir, f"{stem}_spec.png")
                generate_waveform(stem_paths[stem], wave_png, BOTH_STRIP_HEIGHT, args.scale)
                generate_spectrogram(stem_paths[stem], spec_png, BOTH_STRIP_HEIGHT, args.scale)
                print(f"  Tinting: {stem} -> {color}")
                wave_img = tint_spectrogram(wave_png, color, BOTH_STRIP_HEIGHT)
                spec_img = tint_spectrogram(spec_png, color, BOTH_STRIP_HEIGHT)
                tinted.append(combine_stem_strips(wave_img, spec_img))
            elif mode == "waveform":
                png_path = os.path.join(tmp_dir, f"{stem}_wave.png")
                generate_waveform(stem_paths[stem], png_path, SPEC_HEIGHT, args.scale)
                print(f"  Tinting: {stem} -> {color}")
                tinted.append(tint_spectrogram(png_path, color))
            elif mode == "melspectrogram":
                png_path = os.path.join(tmp_dir, f"{stem}_mel.png")
                generate_melspectrogram(stem_paths[stem], png_path)
                print(f"  Tinting: {stem} -> {color}")
                tinted.append(tint_spectrogram(png_path, color))
            else:
                png_path = os.path.join(tmp_dir, f"{stem}_spec.png")
                generate_spectrogram(stem_paths[stem], png_path, SPEC_HEIGHT, args.scale)
                print(f"  Tinting: {stem} -> {color}")
                tinted.append(tint_spectrogram(png_path, color))

        # Step 4: Create header
        print("Creating header...")
        header = create_header(input_path, metadata)

        # Step 5: Compose final image
        print("Compositing stemmogram...")
        final = compose_stemmogram(header, tinted, metadata["duration_s"])

        # Step 6: Save output
        if args.output:
            filename = args.output if args.output.endswith(".png") else args.output + ".png"
            output_path = os.path.join(output_dir, os.path.basename(filename))
        else:
            basename = Path(input_path).stem
            if mode == "both":
                suffix = "_both"
            elif mode == "waveform":
                suffix = "_waveform"
            elif mode == "melspectrogram":
                suffix = "_melspectrogram"
            else:
                suffix = "_stemmogram"
            output_path = os.path.join(output_dir, f"{basename}{suffix}.png")
        final.save(output_path)
        print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
