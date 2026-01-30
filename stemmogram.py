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

from PIL import Image, ImageDraw, ImageFont, ImageOps

STEMS = ["vocals", "other", "bass", "drums"]
STEM_COLORS = {
    "vocals": (255, 140, 0),
    "bass": (0, 80, 255),
    "drums": (140, 140, 140),
    "other": (0, 200, 0),
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
        "--waveform", action="store_true", help="Render waveforms instead of spectrograms"
    )
    parser.add_argument(
        "--both", action="store_true", help="Render waveform + spectrogram combined per stem"
    )
    return parser.parse_args()


def extract_metadata(input_path: str) -> dict:
    """Extract duration, bitrate via ffprobe and loudness via ffmpeg ebur128."""
    # Duration and bitrate
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
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

    minutes = int(duration_s // 60)
    seconds = int(duration_s % 60)
    duration_str = f"{minutes}:{seconds:02d}"
    bitrate_kbps = bitrate_bps // 1000

    # Integrated loudness (LUFS) via ebur128
    loudness_str = "N/A"
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
            loudness_str = f"{float(match.group(1)):.1f} LUFS"
    except Exception:
        pass

    return {
        "duration": duration_str,
        "duration_s": duration_s,
        "bitrate_kbps": bitrate_kbps,
        "loudness": loudness_str,
    }


def separate_stems(input_path: str, tmp_dir: str) -> dict:
    """Run demucs htdemucs to separate audio into stems. Returns dict of stem name -> wav path."""
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

    return stem_paths


def generate_spectrogram(wav_path: str, output_png: str, height: int = SPEC_HEIGHT):
    """Generate a spectrogram PNG using ffmpeg showspectrumpic."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", wav_path,
            "-lavfi", f"showspectrumpic=s={WIDTH}x{height}:legend=0:start=18:stop=18000:win_func=hann:scale=log:fscale=log",
            output_png,
        ],
        capture_output=True,
        check=True,
    )


def generate_waveform(wav_path: str, output_png: str, height: int = SPEC_HEIGHT):
    """Generate a waveform PNG using ffmpeg showwavespic."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", wav_path,
            "-lavfi", f"showwavespic=s={WIDTH}x{height}:colors=white:scale=log",
            output_png,
        ],
        capture_output=True,
        check=True,
    )


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

    stats = f"Duration: {metadata['duration']}    Loudness: {metadata['loudness']}    Bitrate: {metadata['bitrate_kbps']} kbps"
    draw.text((20, 46), stats, fill="gray", font=label_font)

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
    print(f"  Duration: {metadata['duration']}, Bitrate: {metadata['bitrate_kbps']} kbps, Loudness: {metadata['loudness']}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Step 2: Separate stems
        print("Separating stems with htdemucs...")
        stem_paths = separate_stems(input_path, tmp_dir)

        # Step 3: Generate and tint spectrograms/waveforms
        tinted = []
        if args.both:
            mode = "both"
        elif args.waveform:
            mode = "waveform"
        else:
            mode = "spectrogram"
        for stem in STEMS:
            print(f"  Generating {mode}: {stem}...")
            color = STEM_COLORS[stem]
            if args.both:
                wave_png = os.path.join(tmp_dir, f"{stem}_wave.png")
                spec_png = os.path.join(tmp_dir, f"{stem}_spec.png")
                generate_waveform(stem_paths[stem], wave_png, BOTH_STRIP_HEIGHT)
                generate_spectrogram(stem_paths[stem], spec_png, BOTH_STRIP_HEIGHT)
                print(f"  Tinting: {stem} -> {color}")
                wave_img = tint_spectrogram(wave_png, color, BOTH_STRIP_HEIGHT)
                spec_img = tint_spectrogram(spec_png, color, BOTH_STRIP_HEIGHT)
                tinted.append(combine_stem_strips(wave_img, spec_img))
            elif args.waveform:
                png_path = os.path.join(tmp_dir, f"{stem}_wave.png")
                generate_waveform(stem_paths[stem], png_path)
                print(f"  Tinting: {stem} -> {color}")
                tinted.append(tint_spectrogram(png_path, color))
            else:
                png_path = os.path.join(tmp_dir, f"{stem}_spec.png")
                generate_spectrogram(stem_paths[stem], png_path)
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
            if args.both:
                suffix = "_both"
            elif args.waveform:
                suffix = "_waveform"
            else:
                suffix = "_stemmogram"
            output_path = os.path.join(output_dir, f"{basename}{suffix}.png")
        final.save(output_path)
        print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
