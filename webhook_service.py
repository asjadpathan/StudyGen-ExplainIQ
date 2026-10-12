"""
Explain IQ — Webhook Callback Service
=====================================
Dispatches asynchronous webhook callbacks to Spring Boot (or configured target)
upon video generation completion or failure, authenticated via X-Internal-Secret header.
"""

import logging
from typing import Optional
import httpx
from config import SPRING_BOOT_WEBHOOK_URL, INTERNAL_API_SECRET

logger = logging.getLogger(__name__)


async def dispatch_webhook(
    job_id: str,
    status: str,
    video_url: Optional[str] = None,
    subtitles_url: Optional[str] = None,
    duration_seconds: Optional[float] = None,
    error: Optional[str] = None,
    target_url: Optional[str] = None,
) -> bool:
    """
    Dispatches asynchronous webhook to Spring Boot backend or specified target URL.
    Returns True if successfully delivered, False otherwise.
    """
    endpoint = target_url or SPRING_BOOT_WEBHOOK_URL
    if not endpoint:
        logger.info(f"No webhook URL configured; skipping webhook for job {job_id}")
        return False

    payload = {
        "jobId": job_id,
        "status": status,
        "videoUrl": video_url,
        "subtitlesUrl": subtitles_url,
        "durationSeconds": duration_seconds,
        "error": error,
    }

    headers = {
        "X-Internal-Secret": INTERNAL_API_SECRET,
        "Content-Type": "application/json",
        "User-Agent": "ExplainIQ-Microservice/1.2",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            logger.info(f"Webhook dispatched for job {job_id} -> {endpoint} [{resp.status_code}]")
            return True
    except httpx.HTTPStatusError as e:
        logger.warning(
            f"Webhook rejected by {endpoint} for job {job_id}: HTTP {e.response.status_code} - {e.response.text}"
        )
        return False
    except Exception as e:
        logger.warning(f"Unable to post webhook to {endpoint} for job {job_id}: {str(e)}")
        return False
