FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-dejavu-core \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (CPU-only PyTorch to keep image smaller)
RUN pip install --no-cache-dir \
    torch torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir demucs Pillow soundfile numpy librosa

# Pre-download the htdemucs model so it's cached in the image
RUN python3 -c "from demucs.pretrained import get_model; get_model('htdemucs')"

# Copy application
WORKDIR /app
COPY stemmogram.py .

ENTRYPOINT ["python3", "/app/stemmogram.py"]
