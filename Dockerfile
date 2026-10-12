FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libfreetype6-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application assets and modules
COPY assets/ ./assets/
COPY assembler.py config.py database.py llm_service.py \
     main.py manim_templates.py media_service.py slide_service.py \
     s3_service.py webhook_service.py ./

RUN mkdir -p /app/output /app/tmp && chmod -R 777 /app/output /app/tmp

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
