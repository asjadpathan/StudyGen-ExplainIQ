# Explain IQ

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen?style=flat-square)](https://github.com/asjadpathan/explain_iq/actions)
[![Version](https://img.shields.io/badge/version-1.2.0-blue?style=flat-square)](https://github.com/asjadpathan/explain_iq/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg?style=flat-square)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)

Explain IQ is an autonomous, lightweight AI microservice and web studio designed to transform educational concepts into studio-grade 1080p explainer videos in minutes.

---

## Project Description

Producing high-quality educational explainer videos traditionally demands extensive manual effort: writing pedagogical scripts, recording voiceovers, designing presentation slides, curating stock assets, and synchronizing timelines in desktop video editors. Automated solutions frequently rely on heavyweight, resource-intensive rendering pipelines (such as LaTeX, Manim, or Blender) that take minutes per frame and require complex system-level dependencies.

**Explain IQ** solves this bottleneck with an asynchronous, dependency-free rendering engine. It orchestrates:
1. **Google Gemini** for pedagogical storyboarding with structured Pydantic schema enforcement.
2. **Microsoft Edge Neural TTS** for studio-quality voiceover generation and word-boundary subtitle timestamps.
3. **Wikimedia Commons and Pexels APIs** for authentic, hallucination-free educational photography.
4. **Custom Pillow slide engine** for mathematical, typography-driven 1080p visual cards.
5. **MoviePy and NumPy** for zero-copy Ken Burns camera drift and ducked background audio compositing.

The service provides both a production-ready asynchronous REST API with persistent SQLite queue management and a sleek, built-in dark-mode web studio.

---

## Key Features

- **Intelligent Structured Storyboarding**: Leverages Google Gemini (`gemini-flash-lite-latest`) with strict Pydantic schemas to design cohesive multi-scene pedagogical scripts with configurable duration modes (`quick` ~45s, `standard` ~90s, and `deep_dive` ~3–4m).
- **Neural Voiceover & Synchronized Subtitles**: Synthesizes natural speech using Microsoft Edge Neural TTS while streaming exact word-boundary timestamps to produce matching, frame-accurate `.srt` subtitle files.
- **Dependency-Free 1080p Slide Engine**: Renders crisp, modern visual cards using pure Pillow and mathematical centering anchors ($x = 960$), featuring title cards, bullet cards, and callout concept containers without requiring external graphic compilers.
- **Authentic Stock Media Integration**: Queries Wikimedia Commons and Pexels for verified high-resolution photography, eliminating generative AI visual hallucinations and applying centered 1080p cropping with glassmorphic caption pills.
- **Cinematic Ken Burns Compositing**: Applies continuous zero-copy NumPy frame panning and zoom drift across slides and photos, layered with -22 dB ducked ambient audio tracks.
- **Persistent Concurrency & Queue Management**: Backed by SQLite in WAL mode (`jobs.db`) with automatic crash recovery, bounded semaphore worker pools (`asyncio.Semaphore`), live queue positioning, and outbound webhook delivery.
- **Integrated Web Studio Interface**: Serves a responsive, glassmorphic single-page studio application directly from the root endpoint, featuring real-time health telemetry, progress tracking, and an interactive video/subtitle player.

---

## Tech Stack

| Category | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend Framework** | [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+) | Asynchronous REST microservice and static asset serving |
| **ASGI Server** | [Uvicorn](https://www.uvicorn.org/) | High-performance asynchronous HTTP server |
| **Generative AI** | [Google GenAI SDK](https://github.com/google/generative-ai-python) | Gemini Flash-Lite structured storyboard generation |
| **Schema Validation** | [Pydantic v2](https://docs.pydantic.dev/) | Strict data contracts and JSON schema generation |
| **Text-to-Speech** | [edge-tts](https://github.com/rany2/edge-tts) | Microsoft Edge Neural voice synthesis and word timestamps |
| **Audio Processing** | [Mutagen](https://mutagen.readthedocs.io/) | MP3 metadata analysis and audio duration extraction |
| **Graphic Rendering** | [Pillow (PIL)](https://python-pillow.org/) | Pure Python 1080p slide generation with custom typography |
| **Video Assembly** | [MoviePy](https://zulko.github.io/moviepy/) / [NumPy](https://numpy.org/) | Frame compositing, Ken Burns motion, and audio ducking |
| **Persistence** | [SQLite 3](https://sqlite.org/) (WAL Mode) | Persistent job state storage, crash recovery, and queue tracking |
| **Web Frontend** | HTML5, CSS3 (Vanilla), JavaScript | Client studio UI with telemetry and video playback |
| **Deployment** | [Vercel](https://vercel.com/) / Docker-ready | Static frontend rewrites and cloud deployment |

---

## Directory Structure

```text
explain_iq/
├── assets/                 # Shared typography and audio assets
│   ├── audio/              # Ambient background music tracks
│   └── fonts/              # Typography files (Inter-Bold, Inter-Regular)
├── frontend/               # Explain IQ Studio web application
│   ├── api.js              # REST client wrapper and status polling
│   ├── app.js              # UI interaction and state management
│   ├── index.html          # Dashboard interface
│   ├── player.js           # Video player with subtitle synchronization
│   ├── styles.css          # Glassmorphic CSS design system
│   └── vercel.json         # Static hosting configuration
├── output/                 # Generated .mp4 videos and .srt subtitle files
├── tmp/                    # Isolated per-job scratch directories (auto-cleaned)
├── .env.example            # Environment configuration template
├── .gitignore              # Repository exclusion rules
├── assembler.py            # MoviePy video assembly and Ken Burns drift
├── config.py               # Centralized configuration and path resolution
├── database.py             # SQLite persistence layer and job queue
├── llm_service.py          # Gemini structured storyboard generation
├── main.py                 # FastAPI application, REST endpoints, and workers
├── manim_templates.py      # Backward-compatible slide rendering bridge
├── media_service.py        # Edge-TTS speech and stock asset fetchers
├── requirements.txt        # Python backend dependencies
├── slide_service.py        # Native 1080p Pillow graphic card engine
├── CONTRIBUTING.md         # Guidelines for project contributors
└── LICENSE                 # MIT License file
```

---

## Getting Started

### Prerequisites

- **Python**: Version `3.10`, `3.11`, or `3.12` installed.
- **Google Gemini API Key**: Required for storyboard generation. Obtain a key from [Google AI Studio](https://aistudio.google.com/app/apikey).
- **FFmpeg**: Required by MoviePy for video and audio rendering. Ensure `ffmpeg` is installed and accessible in your system `PATH`.
- **Node.js** *(Optional)*: Version `18+` (only needed if building or previewing static frontend deployment scripts independently).
- **Pexels API Key** *(Optional)*: Required only for curated Pexels photography. The service automatically falls back to Wikimedia Commons if omitted.

### Step-by-Step Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/asjadpathan/explain_iq.git
   cd explain_iq
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # On macOS/Linux:
   python3 -m venv venv
   source venv/bin/activate

   # On Windows (PowerShell):
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   Copy `.env.example` to create your local `.env` file:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and set your configuration values:
   ```ini
   # Required: Google Gemini API Key
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini-flash-lite-latest

   # Voice & Output Settings
   TTS_VOICE=en-US-AriaNeural
   VIDEO_WIDTH=1920
   VIDEO_HEIGHT=1080
   VIDEO_FPS=24

   # Optional: Pexels API Key (falls back to Wikimedia Commons if blank)
   PEXELS_API_KEY=

   # Worker Concurrency Limit
   MAX_CONCURRENT_JOBS=2
   ```

### Local Development / Setup Commands

Start the FastAPI application and background worker pool:

```bash
python main.py
```

Or run via Uvicorn with automatic live reload:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Once running:
- **Explain IQ Studio Web UI**: Open [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Documentation**: Open [http://localhost:8000/docs](http://localhost:8000/docs)
- **OpenAPI JSON Schema**: Open [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

---

## Usage Examples

### 1. Terminal / cURL

#### Submit a Video Generation Job
```bash
curl -X POST "http://localhost:8000/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "concept": "Newton'\''s Laws of Motion",
    "target_audience": "high school students",
    "duration_mode": "standard",
    "voice": "en-US-AriaNeural",
    "include_music": false
  }'
```

*Response (`202 Accepted`):*
```json
{
  "job_id": "0ff1a676-cfd4-480d-8660-cd49a3cbe34e",
  "status": "queued",
  "queue_position": 1,
  "message": "Job queued at position 1. Poll /status/0ff1a676-cfd4-480d-8660-cd49a3cbe34e for updates."
}
```

#### Poll Job Status
```bash
curl "http://localhost:8000/status/0ff1a676-cfd4-480d-8660-cd49a3cbe34e"
```

*Response (`200 OK` - Completed):*
```json
{
  "job_id": "0ff1a676-cfd4-480d-8660-cd49a3cbe34e",
  "concept": "Newton's Laws of Motion",
  "target_audience": "high school students",
  "status": "completed",
  "progress_pct": 100,
  "current_stage": "Video generation complete!",
  "video_url": "/download/0ff1a676-cfd4-480d-8660-cd49a3cbe34e",
  "subtitles_url": "/subtitles/0ff1a676-cfd4-480d-8660-cd49a3cbe34e",
  "duration_seconds": 92.4,
  "created_at": "2026-10-12T16:00:52Z",
  "updated_at": "2026-10-12T16:02:18Z"
}
```

#### Download Video and Subtitles
```bash
# Download 1080p MP4
curl -O -J "http://localhost:8000/download/0ff1a676-cfd4-480d-8660-cd49a3cbe34e"

# Download Synchronized SRT
curl -O -J "http://localhost:8000/subtitles/0ff1a676-cfd4-480d-8660-cd49a3cbe34e"
```

---

### 2. Python Client Example

```python
import time
import requests

BASE_URL = "http://localhost:8000"

payload = {
    "concept": "Photosynthesis",
    "target_audience": "middle school students",
    "duration_mode": "quick",
}

response = requests.post(f"{BASE_URL}/generate", json=payload)
response.raise_for_status()
job_id = response.json()["job_id"]
print(f"Enqueued job: {job_id}")

while True:
    status_data = requests.get(f"{BASE_URL}/status/{job_id}").json()
    status = status_data["status"]
    print(f"[{status_data['progress_pct']}%] {status_data['current_stage']}")

    if status == "completed":
        print(f"Video available: {BASE_URL}{status_data['video_url']}")
        print(f"Subtitles available: {BASE_URL}{status_data['subtitles_url']}")
        break
    elif status == "failed":
        print(f"Job failed: {status_data.get('error')}")
        break

    time.sleep(3)
```

---

### 3. JavaScript / Web Client Integration

```javascript
async function generateEducationalVideo(concept) {
  const submitRes = await fetch("http://localhost:8000/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      concept,
      duration_mode: "standard",
      include_music: true,
    }),
  });

  const { job_id } = await submitRes.json();
  console.log(`Job queued with ID: ${job_id}`);

  const pollInterval = setInterval(async () => {
    const statusRes = await fetch(`http://localhost:8000/status/${job_id}`);
    const job = await statusRes.json();

    console.log(`[${job.progress_pct}%] ${job.current_stage}`);

    if (job.status === "completed") {
      clearInterval(pollInterval);
      console.log("Download URL:", `http://localhost:8000${job.video_url}`);
      console.log("Subtitles URL:", `http://localhost:8000${job.subtitles_url}`);
    } else if (job.status === "failed") {
      clearInterval(pollInterval);
      console.error("Pipeline failure:", job.error);
    }
  }, 3000);
}

generateEducationalVideo("The Water Cycle");
```

---

## Contributing

Contributions, bug reports, and suggestions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on code style guidelines, pull request submission processes, and local development standards.

---

## License

This project is licensed under the terms of the MIT License. See [LICENSE](LICENSE) for the complete license text.
