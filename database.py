"""
Explain IQ — SQLite Job Persistence Layer
=========================================
Lightweight, thread-safe persistence using Python's built-in sqlite3.
Survives process restarts with WAL mode enabled for fast concurrent reads.
"""

import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from pathlib import Path

from config import DB_PATH

logger = logging.getLogger(__name__)


def _get_connection() -> sqlite3.Connection:
    """Create a connection with WAL mode and row factory."""
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def init_db() -> None:
    """Initialize database tables and recover interrupted jobs."""
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                concept TEXT NOT NULL,
                target_audience TEXT NOT NULL,
                status TEXT NOT NULL,
                progress_pct INTEGER NOT NULL DEFAULT 0,
                current_stage TEXT NOT NULL DEFAULT 'Waiting in queue',
                error TEXT,
                video_url TEXT,
                subtitles_url TEXT,
                duration_seconds REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);")

        # Mark any non-terminal jobs as failed upon startup
        interrupted_statuses = ("queued", "storyboarding", "generating_audio", "generating_visuals", "assembling")
        placeholders = ",".join("?" for _ in interrupted_statuses)
        now_iso = datetime.now(timezone.utc).isoformat()
        
        cursor = conn.execute(
            f"""
            UPDATE jobs
            SET status = 'failed',
                current_stage = 'Interrupted by service restart',
                error = 'Process restarted before job completed',
                updated_at = ?
            WHERE status IN ({placeholders})
            """,
            (now_iso, *interrupted_statuses)
        )
        if cursor.rowcount > 0:
            logger.info(f"Marked {cursor.rowcount} interrupted jobs as 'failed'")
        conn.commit()
    logger.info(f"Database initialized: {DB_PATH}")


def create_job(job_id: str, concept: str, target_audience: str) -> dict[str, Any]:
    """Insert a new job into the database with initial queued state."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                job_id, concept, target_audience, status,
                progress_pct, current_stage, created_at, updated_at
            ) VALUES (?, ?, ?, 'queued', 0, 'Waiting in queue', ?, ?)
            """,
            (job_id, concept, target_audience, now_iso, now_iso),
        )
        conn.commit()
    return get_job(job_id)  # type: ignore


def update_job(job_id: str, **kwargs) -> None:
    """Update job fields atomically."""
    if not kwargs:
        return
    kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [job_id]

    with _get_connection() as conn:
        conn.execute(f"UPDATE jobs SET {fields} WHERE job_id = ?", values)
        conn.commit()


def get_job(job_id: str) -> Optional[dict[str, Any]]:
    """Retrieve a job by its unique ID."""
    with _get_connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def list_jobs(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """List recent jobs with pagination."""
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


def get_active_job_count() -> int:
    """Count jobs that are currently queued or running."""
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as count FROM jobs WHERE status NOT IN ('completed', 'failed')"
        ).fetchone()
        return row["count"] if row else 0


def get_total_job_count() -> int:
    """Count total jobs recorded in the database."""
    with _get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) as count FROM jobs").fetchone()
        return row["count"] if row else 0


def get_queue_position(job_id: str) -> int:
    """Return 1-based queue position among queued jobs."""
    with _get_connection() as conn:
        row = conn.execute("SELECT created_at FROM jobs WHERE job_id = ? AND status = 'queued'", (job_id,)).fetchone()
        if not row:
            return 0
        job_time = row["created_at"]
        count_row = conn.execute(
            "SELECT COUNT(*) as ahead FROM jobs WHERE status = 'queued' AND created_at <= ?",
            (job_time,)
        ).fetchone()
        return count_row["ahead"] if count_row else 1
