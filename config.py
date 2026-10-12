"""
Explain IQ — Centralized Configuration
=====================================
Centralizes all environment variables with clean local fallbacks
for cloud microservice execution, local dev, and CI/CD environments.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR: Path = Path(__file__).parent.resolve()

# Load environment variables (.env.local takes precedence if present, else .env)
if (BASE_DIR / ".env.local").exists():
    load_dotenv(BASE_DIR / ".env.local")
load_dotenv(BASE_DIR / ".env")

# ── Service & Network ──────────────────────────────────────────
PORT: int = int(os.getenv("PORT", 8000))
INTERNAL_API_SECRET: str = os.getenv("INTERNAL_API_SECRET", "studygen-internal-secret-token")
SPRING_BOOT_WEBHOOK_URL: str = os.getenv("SPRING_BOOT_WEBHOOK_URL", "http://localhost:8080/api/internal/video-status")

# ── Storage Toggle: Local vs AWS S3 ────────────────────────────
USE_S3: bool = os.getenv("USE_S3", "false").lower() == "true"
AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION: str = os.getenv("AWS_REGION", "ap-south-1")
S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "studygen-media-assets")

# ── Engine Settings ────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "")
TTS_VOICE: str = os.getenv("TTS_VOICE", "en-US-AriaNeural")
VIDEO_WIDTH: int = int(os.getenv("VIDEO_WIDTH", 1920))
VIDEO_HEIGHT: int = int(os.getenv("VIDEO_HEIGHT", 1080))
VIDEO_FPS: int = int(os.getenv("VIDEO_FPS", 24))
MAX_CONCURRENT_JOBS: int = int(os.getenv("MAX_CONCURRENT_JOBS", 2))

# ── Directory Paths & Database ─────────────────────────────────
OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "output")).resolve()
TEMP_DIR: Path = Path(os.getenv("TEMP_DIR", BASE_DIR / "tmp")).resolve()
ASSETS_DIR: Path = BASE_DIR / "assets"
FONTS_DIR: Path = ASSETS_DIR / "fonts"
AUDIO_DIR: Path = ASSETS_DIR / "audio"
DB_PATH: Path = Path(os.getenv("DB_PATH", BASE_DIR / "jobs.db")).resolve()

# Ensure directories exist at import time
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
