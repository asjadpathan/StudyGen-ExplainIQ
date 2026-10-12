"""
Explain IQ — FastAPI Video Generation Microservice
==================================================
Production-ready asynchronous API microservice.
Orchestrates Gemini storyboarding, Edge-TTS audio + subtitles,
real stock photo fetching, and MoviePy video assembly.
Features SQLite persistence, bounded worker concurrency, and temp asset isolation.
"""

import asyncio
import json
import logging
import re
import shutil
import urllib.request
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal, Optional, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import (
    OUTPUT_DIR,
    TEMP_DIR,
    TTS_VOICE,
    MAX_CONCURRENT_JOBS,
)
import database
from llm_service import generate_storyboard
from slide_service import render_slide
from media_service import generate_tts, fetch_stock_image
from assembler import SceneAssets, assemble_final_video

# ── Logging Setup ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-18s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("explain_iq")

# ── Worker Concurrency Limiter ─────────────────────────────────

job_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)


# ── Subtitle Helper: Merge Scene SRTs ──────────────────────────

def _format_srt_timestamp(seconds: float) -> str:
    """Format seconds into SRT timestamp: HH:MM:SS,mmm"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def _parse_srt_timestamp(ts: str) -> float:
    """Parse SRT timestamp into seconds."""
    parts = ts.strip().replace(",", ".").split(":")
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return 0.0


def merge_scene_srts(scene_data: List[tuple[Path, float]], output_srt_path: Path) -> Optional[Path]:
    """
    Merge individual scene SRT files with cumulative timestamp offsets
    into a unified video subtitle file.
    """
    all_entries = []
    cumulative_offset = 0.0
    counter = 1

    time_pattern = re.compile(r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})")

    for srt_path, duration in scene_data:
        if srt_path.exists():
            content = srt_path.read_text(encoding="utf-8")
            blocks = content.strip().split("\n\n")
            for block in blocks:
                lines = block.strip().split("\n")
                if len(lines) >= 2:
                    match = time_pattern.search(lines[1] if len(lines) > 1 and "-->" in lines[1] else lines[0])
                    if match:
                        start_sec = _parse_srt_timestamp(match.group(1)) + cumulative_offset
                        end_sec = _parse_srt_timestamp(match.group(2)) + cumulative_offset
                        text = "\n".join(lines[2:] if "-->" in lines[1] else lines[1:])
                        if text:
                            all_entries.append(
                                f"{counter}\n{_format_srt_timestamp(start_sec)} --> {_format_srt_timestamp(end_sec)}\n{text}"
                            )
                            counter += 1
        cumulative_offset += duration

    if all_entries:
        output_srt_path.parent.mkdir(parents=True, exist_ok=True)
        output_srt_path.write_text("\n\n".join(all_entries) + "\n", encoding="utf-8")
        return output_srt_path
    return None


# ── Webhook Dispatcher ─────────────────────────────────────────

async def dispatch_webhook(webhook_url: str, payload: dict) -> None:
    """Post job status callback to external webhook."""
    def _send():
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                webhook_url,
                data=req_data,
                headers={"Content-Type": "application/json", "User-Agent": "ExplainIQ/1.0"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                logger.info(f"Webhook delivered to {webhook_url} (HTTP {resp.status})")
        except Exception as e:
            logger.warning(f"Failed to deliver webhook to {webhook_url}: {e}")

    await asyncio.to_thread(_send)


# ── Pydantic Request/Response Models ──────────────────────────

class GenerateRequest(BaseModel):
    concept: str = Field(
        ...,
        description="The educational concept to create a video about",
        min_length=3,
        max_length=500,
        examples=["Newton's Laws of Motion", "Photosynthesis", "Quantum Computing"],
    )
    target_audience: str = Field(
        default="high school students",
        description="Target viewer audience demographic",
        examples=["high school students", "college freshmen", "middle school students"],
    )
    duration_mode: Literal["quick", "standard", "deep_dive"] = Field(
        default="standard",
        description="Video depth: 'quick' (~45s), 'standard' (~90s), or 'deep_dive' (~3m)",
    )
    voice: Optional[str] = Field(
        default=TTS_VOICE,
        description="Edge TTS voice name (e.g., en-US-AriaNeural, en-US-GuyNeural)",
    )
    include_music: bool = Field(
        default=False,
        description="Whether to layer subtle background music under narration",
    )
    webhook_url: Optional[str] = Field(
        default=None,
        description="Optional HTTP URL to receive POST callback upon job completion or failure",
    )


class GenerateResponse(BaseModel):
    job_id: str
    status: str
    queue_position: int
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    concept: str
    target_audience: str
    status: str
    progress_pct: int
    current_stage: str
    queue_position: Optional[int] = None
    error: Optional[str] = None
    video_url: Optional[str] = None
    subtitles_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    created_at: str
    updated_at: str


# ── FastAPI Application Lifecycle ─────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🎬 Explain IQ Production Microservice starting up")
    database.init_db()
    logger.info(f"   Output directory: {OUTPUT_DIR}")
    logger.info(f"   Temp directory: {TEMP_DIR}")
    logger.info(f"   Max concurrent jobs: {MAX_CONCURRENT_JOBS}")

    # Sweep stale temp directories on startup
    try:
        from config import BASE_DIR
        for item in TEMP_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
        for p in BASE_DIR.glob("*TEMP_MPY_*"):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        stray_python = BASE_DIR / "python"
        if stray_python.is_file() and stray_python.stat().st_size == 0:
            try:
                stray_python.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Startup temp cleanup warning: {e}")

    yield
    logger.info("🛑 Explain IQ shutting down")


app = FastAPI(
    title="Explain IQ Video Generation API",
    description=(
        "Production-ready video generation microservice. "
        "Transforms educational concepts into 1080p explainer videos with Gemini storyboarding, "
        "Edge-TTS speech, real stock photography, and MoviePy assembly."
    ),
    version="1.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ──────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint reporting active queue, capacity, and storage stats."""
    active_count = database.get_active_job_count()
    total_count = database.get_total_job_count()
    output_files = len(list(OUTPUT_DIR.glob("*.mp4")))

    return {
        "status": "healthy",
        "service": "explain_iq",
        "active_jobs": active_count,
        "total_jobs": total_count,
        "concurrency_limit": MAX_CONCURRENT_JOBS,
        "completed_videos_stored": output_files,
    }


@app.post("/generate", status_code=202, response_model=GenerateResponse)
async def generate_video(request: GenerateRequest):
    """
    Submit a video generation job.
    Returns immediately with job_id and queue status.
    """
    job_id = str(uuid.uuid4())

    # Record job in persistent database
    database.create_job(job_id, request.concept, request.target_audience)
    queue_pos = database.get_queue_position(job_id)

    # Dispatch to background task runner with concurrency control
    asyncio.create_task(
        run_pipeline_worker(
            job_id=job_id,
            concept=request.concept,
            target_audience=request.target_audience,
            duration_mode=request.duration_mode,
            voice=request.voice or TTS_VOICE,
            include_music=request.include_music,
            webhook_url=request.webhook_url,
        )
    )

    logger.info(f"Job {job_id[:8]} enqueued (position: {queue_pos}) for: '{request.concept}'")

    return GenerateResponse(
        job_id=job_id,
        status="queued",
        queue_position=queue_pos,
        message=f"Job queued at position {queue_pos}. Poll /status/{job_id} for updates.",
    )


@app.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Get the current progress and status of a video job."""
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    queue_pos = database.get_queue_position(job_id) if job["status"] == "queued" else None

    return JobStatusResponse(
        job_id=job["job_id"],
        concept=job["concept"],
        target_audience=job["target_audience"],
        status=job["status"],
        progress_pct=job["progress_pct"],
        current_stage=job["current_stage"],
        queue_position=queue_pos,
        error=job["error"],
        video_url=job["video_url"],
        subtitles_url=job["subtitles_url"],
        duration_seconds=job["duration_seconds"],
        created_at=job["created_at"],
        updated_at=job["updated_at"],
    )


@app.get("/download/{job_id}")
async def download_video(job_id: str):
    """Download the completed 1080p MP4 video file."""
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job["status"] == "failed":
        raise HTTPException(status_code=500, detail=f"Job failed: {job['error']}")

    if job["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Video not ready. Current status: {job['status']} ({job['progress_pct']}%)",
        )

    video_path = OUTPUT_DIR / f"{job_id}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found on disk")

    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        filename=f"explain_iq_{job_id[:8]}.mp4",
    )


@app.get("/subtitles/{job_id}")
async def download_subtitles(job_id: str):
    """Download the generated .srt subtitles file."""
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    srt_path = OUTPUT_DIR / f"{job_id}.srt"
    if not srt_path.exists():
        raise HTTPException(status_code=404, detail="Subtitles not found for this job")

    return FileResponse(
        path=str(srt_path),
        media_type="application/x-subrip",
        filename=f"explain_iq_{job_id[:8]}.srt",
    )


@app.get("/jobs")
async def list_recent_jobs(limit: int = Query(20, ge=1, le=100)):
    """List recent video generation jobs."""
    return database.list_jobs(limit=limit)


# ── Frontend Static Files (Explain IQ Studio) ──────────────────
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")



# ── Pipeline Worker with Concurrency Semaphore ────────────────

async def run_pipeline_worker(
    job_id: str,
    concept: str,
    target_audience: str,
    duration_mode: str,
    voice: str,
    include_music: bool,
    webhook_url: Optional[str] = None,
) -> None:
    """Wrapper that enforces the concurrency semaphore and drives the pipeline."""
    # Update status to waiting if workers are busy
    q_pos = database.get_queue_position(job_id)
    if q_pos > 1:
        database.update_job(
            job_id,
            current_stage=f"Queued: waiting for worker (position {q_pos})",
        )

    async with job_semaphore:
        job_dir = TEMP_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        try:
            # ── Stage 1: Storyboard ────────────────────────────
            database.update_job(
                job_id,
                status="storyboarding",
                progress_pct=5,
                current_stage="Generating storyboard with Gemini...",
            )

            storyboard = await generate_storyboard(
                concept=concept,
                target_audience=target_audience,
                duration_mode=duration_mode,
            )
            num_scenes = len(storyboard.scenes)
            logger.info(f"[{job_id[:8]}] Storyboard ready: '{storyboard.title}' ({num_scenes} scenes)")

            database.update_job(
                job_id,
                progress_pct=15,
                current_stage=f"Storyboard ready: {num_scenes} scenes",
            )

            # ── Stage 2: Audio & Subtitle Synthesis ───────────
            database.update_job(
                job_id,
                status="generating_audio",
                progress_pct=20,
                current_stage="Synthesizing neural voiceover & subtitles...",
            )

            audio_dir = job_dir / "audio"
            audio_dir.mkdir(exist_ok=True)
            scene_durations: dict[int, float] = {}
            scene_srt_entries: list[tuple[Path, float]] = []

            for i, scene in enumerate(storyboard.scenes):
                audio_path = audio_dir / f"scene_{scene.scene_id}.mp3"
                srt_path = audio_dir / f"scene_{scene.scene_id}.srt"

                _, duration = await generate_tts(
                    text=scene.narration_text,
                    output_path=audio_path,
                    voice=voice,
                    srt_output_path=srt_path,
                )
                scene_durations[scene.scene_id] = duration
                scene_srt_entries.append((srt_path, duration))

                progress = 20 + int((i + 1) / num_scenes * 20)
                database.update_job(
                    job_id,
                    progress_pct=progress,
                    current_stage=f"Voiceover: scene {i + 1}/{num_scenes} ({duration:.1f}s)",
                )

            # ── Stage 3: Visual Generation ────────────────────
            database.update_job(
                job_id,
                status="generating_visuals",
                progress_pct=40,
                current_stage="Rendering slides and fetching stock images...",
            )

            visuals_dir = job_dir / "visuals"
            visuals_dir.mkdir(exist_ok=True)
            images_dir = job_dir / "images"
            images_dir.mkdir(exist_ok=True)

            scene_assets: list[SceneAssets] = []

            for i, scene in enumerate(storyboard.scenes):
                duration = scene_durations[scene.scene_id]
                audio_path = audio_dir / f"scene_{scene.scene_id}.mp3"

                if scene.visual_type == "slide":
                    meta = scene.slide_metadata or scene.manim_metadata
                    template = meta.template if meta else ("title_card" if i == 0 else "text_bullet")
                    title = meta.title if meta else storyboard.title
                    subtitle = meta.subtitle if meta else None
                    bullets = meta.bullet_points if meta else []
                    key_text = meta.key_text if (meta and hasattr(meta, "key_text")) else None
                    color = meta.highlight_color if meta else "#38BDF8"

                    config_data = {
                        "title": title,
                        "subtitle": subtitle,
                        "bullet_points": bullets,
                        "key_text": key_text,
                        "highlight_color": color,
                        "duration": duration,
                    }

                    visual_path = await asyncio.to_thread(
                        render_slide,
                        template,
                        config_data,
                        visuals_dir,
                        scene.scene_id,
                    )
                else:
                    # Real stock image fetching
                    image_path = images_dir / f"scene_{scene.scene_id}.png"
                    query = scene.image_metadata.search_query if scene.image_metadata else concept
                    alt = scene.image_metadata.alt_text if scene.image_metadata else f"Scene {scene.scene_id}"

                    visual_path = await fetch_stock_image(
                        search_query=query,
                        output_path=image_path,
                        alt_text=alt,
                    )

                scene_assets.append(
                    SceneAssets(
                        scene_id=scene.scene_id,
                        visual_path=Path(visual_path),
                        audio_path=audio_path,
                        audio_duration=duration,
                        visual_type=scene.visual_type,
                    )
                )

                progress = 40 + int((i + 1) / num_scenes * 35)
                database.update_job(
                    job_id,
                    progress_pct=progress,
                    current_stage=f"Visuals: scene {i + 1}/{num_scenes} ({scene.visual_type})",
                )

            # ── Stage 4: Video Assembly ───────────────────────
            database.update_job(
                job_id,
                status="assembling",
                progress_pct=80,
                current_stage="Assembling video with Ken Burns motion & transitions...",
            )

            output_video_path = OUTPUT_DIR / f"{job_id}.mp4"

            await asyncio.to_thread(
                assemble_final_video,
                scene_assets,
                output_video_path,
                include_music=include_music,
                enable_motion=True,
            )

            # Assemble merged SRT subtitles
            output_srt_path = OUTPUT_DIR / f"{job_id}.srt"
            merged_srt = merge_scene_srts(scene_srt_entries, output_srt_path)
            subtitles_url = f"/subtitles/{job_id}" if merged_srt else None

            total_duration = sum(scene_durations.values())

            # ── Complete ──────────────────────────────────────
            database.update_job(
                job_id,
                status="completed",
                progress_pct=100,
                current_stage="Video generation complete!",
                video_url=f"/download/{job_id}",
                subtitles_url=subtitles_url,
                duration_seconds=round(total_duration, 1),
            )

            logger.info(f"[{job_id[:8]}] ✅ Video generation completed: {output_video_path}")

            # Send Webhook if configured
            if webhook_url:
                webhook_payload = {
                    "event": "video.completed",
                    "job_id": job_id,
                    "concept": concept,
                    "status": "completed",
                    "video_url": f"/download/{job_id}",
                    "subtitles_url": subtitles_url,
                    "duration_seconds": round(total_duration, 1),
                }
                asyncio.create_task(dispatch_webhook(webhook_url, webhook_payload))

        except Exception as e:
            logger.error(f"[{job_id[:8]}] ❌ Pipeline failed: {e}", exc_info=True)
            database.update_job(
                job_id,
                status="failed",
                current_stage="Pipeline failed",
                error=str(e),
            )
            if webhook_url:
                webhook_payload = {
                    "event": "video.failed",
                    "job_id": job_id,
                    "concept": concept,
                    "status": "failed",
                    "error": str(e),
                }
                asyncio.create_task(dispatch_webhook(webhook_url, webhook_payload))

        finally:
            # Always clean up temp files
            try:
                shutil.rmtree(job_dir, ignore_errors=True)
                logger.info(f"[{job_id[:8]}] Temp directory cleaned up")
            except Exception as e:
                logger.warning(f"[{job_id[:8]}] Cleanup warning: {e}")


# ── Direct Run: python main.py ─────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
