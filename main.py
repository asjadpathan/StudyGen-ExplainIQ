"""
Explain IQ — Production Video Generation Microservice
======================================================
Cloud-optimized, CI/CD-ready asynchronous video generation worker.
Orchestrates Gemini storyboarding, Edge-TTS audio + subtitles,
real stock photo fetching, and MoviePy video assembly.
Features dual-mode S3/local storage, Spring Boot webhook integration,
and bounded worker concurrency.
"""

import asyncio
import logging
import os
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, BackgroundTasks, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import (
    OUTPUT_DIR,
    TEMP_DIR,
    TTS_VOICE,
    MAX_CONCURRENT_JOBS,
    INTERNAL_API_SECRET,
    USE_S3,
    PORT,
)
import database
from llm_service import generate_storyboard
from slide_service import render_slide
from media_service import generate_tts, fetch_stock_image
from assembler import SceneAssets, assemble_final_video
from s3_service import handle_artifacts
from webhook_service import dispatch_webhook

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


# ── Pydantic Request & Response Models ─────────────────────────
class GenerateRequest(BaseModel):
    concept: str = Field(
        ...,
        description="The educational concept to create a video about",
        min_length=3,
        max_length=500,
        examples=["Newton's Laws of Motion", "Photosynthesis", "Quantum Computing"],
    )
    target_audience: Optional[str] = Field(
        default="students",
        description="Target viewer audience demographic",
        examples=["students", "high school students", "college freshmen"],
    )
    duration_mode: Optional[str] = Field(
        default="standard",
        description="Video depth: 'quick' (~45s), 'standard' (~90s), or 'deep_dive' (~3m)",
    )
    voice: Optional[str] = Field(
        default="en-US-AriaNeural",
        description="Edge TTS voice name",
    )
    include_music: Optional[bool] = Field(
        default=False,
        description="Whether to layer subtle background music under narration",
    )
    webhook_url: Optional[str] = Field(
        default=None,
        description="Optional custom HTTP webhook URL callback",
    )


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
    logger.info("🎬 Explain IQ Microservice starting up")
    database.init_db()
    logger.info(f"   Storage mode: {'AWS S3' if USE_S3 else 'Local Disk'}")
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
    except Exception as e:
        logger.warning(f"Startup temp cleanup warning: {e}")

    yield
    logger.info("🛑 Explain IQ Microservice shutting down")


app = FastAPI(
    title="Explain IQ Microservice",
    description="Cloud-optimized asynchronous video generation microservice serving StudyGen.",
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


# ── Pipeline Worker with Concurrency Semaphore ────────────────
async def run_pipeline_worker(job_id: str, req: GenerateRequest) -> None:
    """Orchestrates storyboarding, synthesis, assembly, artifact upload, and webhooks."""
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
            # ── 1. Storyboarding via Gemini ────────────────────
            database.update_job(
                job_id,
                status="storyboarding",
                progress_pct=5,
                current_stage="Generating storyboard with Gemini...",
            )

            storyboard = await generate_storyboard(
                concept=req.concept,
                target_audience=req.target_audience or "students",
                duration_mode=req.duration_mode or "standard",
            )
            num_scenes = len(storyboard.scenes)
            logger.info(f"[{job_id[:8]}] Storyboard ready: '{storyboard.title}' ({num_scenes} scenes)")

            database.update_job(
                job_id,
                progress_pct=15,
                current_stage=f"Storyboard ready: {num_scenes} scenes",
            )

            # ── 2. TTS Voiceover & Subtitles ──────────────────
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

            selected_voice = req.voice or TTS_VOICE

            for i, scene in enumerate(storyboard.scenes):
                audio_path = audio_dir / f"scene_{scene.scene_id}.mp3"
                srt_path = audio_dir / f"scene_{scene.scene_id}.srt"

                _, duration = await generate_tts(
                    text=scene.narration_text,
                    output_path=audio_path,
                    voice=selected_voice,
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

            # ── 3. Visuals via Pillow & Stock Images ──────────
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
                    image_path = images_dir / f"scene_{scene.scene_id}.png"
                    query = scene.image_metadata.search_query if scene.image_metadata else req.concept
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

            # ── 4. Assembly & Ken Burns via MoviePy ────────────
            database.update_job(
                job_id,
                status="assembling",
                progress_pct=80,
                current_stage="Assembling video with Ken Burns motion & transitions...",
            )

            local_video_path = OUTPUT_DIR / f"{job_id}.mp4"

            await asyncio.to_thread(
                assemble_final_video,
                scene_assets,
                local_video_path,
                include_music=bool(req.include_music),
                enable_motion=True,
            )

            # Subtitle merge
            local_srt_path = OUTPUT_DIR / f"{job_id}.srt"
            merged_srt = merge_scene_srts(scene_srt_entries, local_srt_path)
            total_duration = sum(scene_durations.values())

            # ── 5. Artifact Upload & Scratch Disk Purge ───────
            urls = handle_artifacts(job_id, local_video_path, local_srt_path if merged_srt else None)
            video_url = urls.get("video_url")
            subtitles_url = urls.get("subtitles_url")

            # ── 6. Update Database State ──────────────────────
            database.update_job(
                job_id,
                status="completed",
                progress_pct=100,
                current_stage="Video generation complete!",
                video_url=video_url,
                subtitles_url=subtitles_url,
                duration_seconds=round(total_duration, 1),
            )

            logger.info(f"[{job_id[:8]}] ✅ Video completed successfully: {video_url}")

            # ── 7. Webhook Delivery to Spring Boot ────────────
            await dispatch_webhook(
                job_id=job_id,
                status="COMPLETED",
                video_url=video_url,
                subtitles_url=subtitles_url,
                duration_seconds=round(total_duration, 1),
                target_url=req.webhook_url,
            )

        except Exception as exc:
            error_msg = str(exc)
            logger.error(f"[{job_id[:8]}] ❌ Pipeline failed: {error_msg}", exc_info=True)
            database.update_job(
                job_id,
                status="failed",
                current_stage="Pipeline failed",
                error=error_msg,
            )

            # Webhook failure delivery
            await dispatch_webhook(
                job_id=job_id,
                status="FAILED",
                error=error_msg,
                target_url=req.webhook_url,
            )

        finally:
            # Sweep temporary job scratch folder
            try:
                shutil.rmtree(job_dir, ignore_errors=True)
                logger.info(f"[{job_id[:8]}] Scratch directory cleared")
            except Exception as e:
                logger.warning(f"[{job_id[:8]}] Cleanup warning: {e}")


# ── REST API Endpoints ─────────────────────────────────────────

@app.get("/health")
def health():
    """Health check endpoint reporting microservice status and capacity."""
    active_count = database.get_active_job_count()
    total_count = database.get_total_job_count()
    return {
        "status": "ok",
        "service": "explain_iq",
        "storage_mode": "s3" if USE_S3 else "local",
        "active_jobs": active_count,
        "total_jobs": total_count,
        "concurrency_limit": MAX_CONCURRENT_JOBS,
    }


@app.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_video(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    x_internal_secret: Optional[str] = Header(None),
):
    """
    Queue video generation.
    Supports optional shared-secret enforcement via X-Internal-Secret header.
    """
    if x_internal_secret and x_internal_secret != INTERNAL_API_SECRET:
        raise HTTPException(status_code=403, detail="Invalid internal secret")

    job_id = str(uuid.uuid4())
    database.create_job(job_id, req.concept, req.target_audience or "students")
    queue_pos = database.get_queue_position(job_id)

    background_tasks.add_task(run_pipeline_worker, job_id, req)
    logger.info(f"Job {job_id[:8]} queued for concept: '{req.concept}'")

    return {
        "job_id": job_id,
        "status": "queued",
        "queue_position": queue_pos,
        "message": f"Job {job_id} queued successfully.",
    }


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
    """Download local video or redirect to S3 asset."""
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

    # If already published to S3, redirect directly
    if job.get("video_url") and job["video_url"].startswith("http"):
        return RedirectResponse(url=job["video_url"])

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
    """Download local subtitles or redirect to S3 asset."""
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job.get("subtitles_url") and job["subtitles_url"].startswith("http"):
        return RedirectResponse(url=job["subtitles_url"])

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


# ── Frontend Static Files (Optional Studio UI) ────────────────
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


# ── Direct Run ────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=True,
    )
