"""
Explain IQ — Centralized Configuration
=====================================
Loads all settings from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent / ".env")

# ── LLM Configuration ──────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

# ── TTS Configuration ──────────────────────────────────────────
TTS_VOICE: str = os.getenv("TTS_VOICE", "en-US-AriaNeural")

# ── Video Output Settings ──────────────────────────────────────
VIDEO_WIDTH: int = int(os.getenv("VIDEO_WIDTH", "1920"))
VIDEO_HEIGHT: int = int(os.getenv("VIDEO_HEIGHT", "1080"))
VIDEO_FPS: int = int(os.getenv("VIDEO_FPS", "24"))

# ── Media & Image Configuration ────────────────────────────────
PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "")

# ── Microservice & Worker Settings ─────────────────────────────
MAX_CONCURRENT_JOBS: int = int(os.getenv("MAX_CONCURRENT_JOBS", "1"))

# ── Directory Paths & Database ─────────────────────────────────
BASE_DIR: Path = Path(__file__).parent.resolve()
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

