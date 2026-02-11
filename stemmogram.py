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
        "--scale", default="cbrt", choices=["lin", "log", "sqrt", "cbrt"],
        help="Scaling method for waveform/spectrogram: lin, log, sqrt, or cbrt (default: cbrt)"
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

    # Integrated loudness (LUFS) and loudness range (LRA) via ebur128
    lufs_value = None
    lra_value = None
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
        match_lra = re.search(r"LRA:\s+([-\d.]+)\s+LU", stderr)
        if match_lra:
            lra_value = float(match_lra.group(1))
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
        "lra": lra_value,
        "sample_rate": sample_rate,
        "mean_volume": mean_volume,
        "max_volume": max_volume,
    }


def measure_stem_loudness(wav_path: str) -> dict:
    """Measure LUFS and LRA for a single stem WAV file."""
    lufs_value = None
    lra_value = None
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", wav_path, "-af", "ebur128=framelog=verbose", "-f", "null", "-"],
            capture_output=True,
            text=True,
        )
        stderr = result.stderr
        match = re.search(r"I:\s+([-\d.]+)\s+LUFS", stderr)
        if match:
            lufs_value = float(match.group(1))
        match_lra = re.search(r"LRA:\s+([-\d.]+)\s+LU", stderr)
        if match_lra:
            lra_value = float(match_lra.group(1))
    except Exception:
        pass
    return {"lufs": lufs_value, "lra": lra_value}


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


def create_lufs_range_bar(lufs_value: float, lra_value: float = None, width: int = 240, height: int = 28) -> Image.Image:
    """
    Create range bar visualization showing LUFS position and LRA width.
    Scale: -30 to 0 LUFS

    Bar position = LUFS value
    Bar width = LRA (loudness range) - wider = more dynamic

    Color zones (bar colored by which zones it spans):
      > -9   : red (too loud)
      -9 to -14: orange (loud)
      -14 to -18: green (streaming target)
      < -18  : blue (quiet)
    """
    img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    # Scale parameters
    lufs_min, lufs_max = -30, 0
    scale_range = lufs_max - lufs_min  # 30

    def lufs_to_x(lufs):
        return int((lufs - lufs_min) / scale_range * width)

    # Draw background track
    track_height = 8
    track_y = (height - track_height) // 2
    draw.rectangle([0, track_y, width - 1, track_y + track_height - 1], fill=(220, 220, 220, 255))

    # Draw tick marks at -24, -18, -14, -9
    tick_values = [-24, -18, -14, -9]
    for tick in tick_values:
        x = lufs_to_x(tick)
        draw.line([(x, track_y - 2), (x, track_y + track_height + 1)], fill=(180, 180, 180, 255), width=1)

    # Clamp LUFS to range
    lufs_clamped = max(lufs_min, min(lufs_max, lufs_value))

    # Default LRA if not provided
    if lra_value is None:
        lra_value = 6  # typical value
    lra_clamped = max(2, min(20, lra_value))  # clamp to reasonable range

    # Calculate bar LUFS range
    bar_lufs_left = lufs_clamped - lra_clamped / 2
    bar_lufs_right = lufs_clamped + lra_clamped / 2

    # Bar pixel positions
    bar_height = height - 4
    bar_y = 2
    bar_left = max(0, lufs_to_x(bar_lufs_left))
    bar_right = min(width - 1, lufs_to_x(bar_lufs_right))

    # Color zones with their LUFS boundaries
    zones = [
        (-30, -18, (70, 130, 180)),   # blue - quiet
        (-18, -14, (50, 180, 50)),    # green - streaming target
        (-14, -9, (255, 165, 0)),     # orange - loud
        (-9, 0, (220, 50, 50)),       # red - too loud
    ]

    # Draw each zone segment that overlaps with the bar
    for zone_min, zone_max, color in zones:
        # Find overlap between bar range and zone range
        overlap_min = max(bar_lufs_left, zone_min)
        overlap_max = min(bar_lufs_right, zone_max)

        if overlap_min < overlap_max:
            x_left = max(bar_left, lufs_to_x(overlap_min))
            x_right = min(bar_right, lufs_to_x(overlap_max))
            if x_left < x_right:
                draw.rectangle([x_left, bar_y, x_right, bar_y + bar_height - 1], fill=color + (255,))

    # Draw center marker (LUFS position)
    center_x = lufs_to_x(lufs_clamped)
    marker_width = 3
    marker_left = max(bar_left, center_x - marker_width // 2)
    marker_right = min(bar_right, center_x + marker_width // 2)
    draw.rectangle([marker_left, bar_y, marker_right, bar_y + bar_height - 1], fill=(255, 255, 255, 200))

    # Draw bracket ends
    bracket_height = 6
    draw.line([(bar_left, bar_y), (bar_left, bar_y + bracket_height)], fill=(0, 0, 0, 180), width=2)
    draw.line([(bar_right, bar_y), (bar_right, bar_y + bracket_height)], fill=(0, 0, 0, 180), width=2)
    draw.line([(bar_left, bar_y + bar_height - 1), (bar_left, bar_y + bar_height - 1 - bracket_height)], fill=(0, 0, 0, 180), width=2)
    draw.line([(bar_right, bar_y + bar_height - 1), (bar_right, bar_y + bar_height - 1 - bracket_height)], fill=(0, 0, 0, 180), width=2)

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

    # LUFS/LRA range bar below project name
    lufs = metadata.get("lufs")
    lra = metadata.get("lra")
    if lufs is not None:
        meter_width = 200
        meter_height = 28
        meter_img = create_lufs_range_bar(lufs, lra, meter_width, meter_height)
        meter_x = WIDTH - meter_width - 20
        meter_y = 28
        header.paste(meter_img, (meter_x, meter_y), meter_img)
        # LUFS/LRA text to the left of meter
        lra_str = f", {lra:.0f} LU" if lra is not None else ""
        lufs_text = f"{lufs:.1f} LUFS{lra_str}"
        try:
            lufs_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        except OSError:
            lufs_font = label_font
        lufs_bbox = draw.textbbox((0, 0), lufs_text, font=lufs_font)
        lufs_w = lufs_bbox[2] - lufs_bbox[0]
        draw.text((meter_x - lufs_w - 10, meter_y + 5), lufs_text, fill="gray", font=lufs_font)

    return header


def compose_stemmogram(header: Image.Image, spectrograms: list, duration_s: float, stem_metadata: dict = None) -> Image.Image:
    """Stack header + 4 spectrograms into a 1920x1080 image."""
    final = Image.new("RGB", (WIDTH, TOTAL_HEIGHT), "white")
    final.paste(header, (0, 0))

    try:
        label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        stats_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        time_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except OSError:
        label_font = ImageFont.load_default()
        stats_font = label_font
        time_font = label_font

    draw = ImageDraw.Draw(final)
    for i, spec in enumerate(spectrograms):
        y = HEADER_HEIGHT + i * SPEC_HEIGHT
        final.paste(spec, (0, y))
        stem_name = STEMS[i]

        # Build label with loudness stats
        label_text = stem_name
        stats_text = ""
        if stem_metadata and stem_name in stem_metadata:
            meta = stem_metadata[stem_name]
            if meta.get("lufs") is not None:
                lra_str = f", {meta['lra']:.0f} LU" if meta.get("lra") is not None else ""
                stats_text = f"  {meta['lufs']:.1f} LUFS{lra_str}"

        # White shadow for readability over dark waveforms
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    draw.text((10 + dx, y + 6 + dy), label_text, fill="white", font=label_font)
        draw.text((10, y + 6), label_text, fill="black", font=label_font)

        # Stats text after stem name
        if stats_text:
            label_bbox = draw.textbbox((10, y + 6), label_text, font=label_font)
            stats_x = label_bbox[2] + 5
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        draw.text((stats_x + dx, y + 9 + dy), stats_text, fill="white", font=stats_font)
            draw.text((stats_x, y + 9), stats_text, fill=(80, 80, 80), font=stats_font)

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
    lra_str = f", LRA: {metadata['lra']:.1f} LU" if metadata['lra'] is not None else ""
    print(f"  Duration: {metadata['duration']}, Bitrate: {metadata['bitrate_kbps']} kbps, Loudness: {lufs_str}{lra_str}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Step 2: Separate stems
        print("Separating stems with htdemucs...")
        stem_paths = separate_stems(input_path, tmp_dir, args.cache)

        # Step 2b: Measure loudness for each stem (with caching)
        print("Measuring stem loudness...")
        stem_metadata = {}
        cache_dir = "/cache"
        metadata_cache_path = os.path.join(cache_dir, args.cache, "stem_metadata.json") if args.cache else None

        # Try to load cached metadata
        if metadata_cache_path and os.path.isfile(metadata_cache_path):
            try:
                with open(metadata_cache_path, "r") as f:
                    stem_metadata = json.load(f)
                print("  Using cached stem metadata")
            except Exception:
                stem_metadata = {}

        # Measure any missing stems
        for stem in STEMS:
            if stem not in stem_metadata or stem_metadata[stem].get("lufs") is None:
                stem_metadata[stem] = measure_stem_loudness(stem_paths[stem])
            lufs = stem_metadata[stem].get("lufs")
            lra = stem_metadata[stem].get("lra")
            lufs_str = f"{lufs:.1f} LUFS" if lufs else "N/A"
            lra_str = f", {lra:.1f} LU" if lra else ""
            print(f"  {stem}: {lufs_str}{lra_str}")

        # Save to cache if cache_id provided
        if metadata_cache_path:
            try:
                os.makedirs(os.path.dirname(metadata_cache_path), exist_ok=True)
                with open(metadata_cache_path, "w") as f:
                    json.dump(stem_metadata, f)
            except Exception:
                pass

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
        final = compose_stemmogram(header, tinted, metadata["duration_s"], stem_metadata)

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
