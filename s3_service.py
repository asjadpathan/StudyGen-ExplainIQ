"""
Explain IQ — S3 Storage Service
===============================
Handles artifact publishing and disk cleanup.
Dual-mode storage: uploads artifacts to AWS S3 in production with scratch cleanup,
or retains files locally during development (USE_S3=false).
"""

import os
import logging
from pathlib import Path
from typing import Optional, Union
try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    boto3 = None
    ClientError = Exception
    BOTO3_AVAILABLE = False

from config import (
    USE_S3,
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    S3_BUCKET_NAME,
)

logger = logging.getLogger(__name__)

s3_client = None
if USE_S3:
    if not BOTO3_AVAILABLE:
        logger.error("USE_S3 is true but 'boto3' is not installed. Run: pip install boto3")
    else:
        try:
            if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
                s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                    region_name=AWS_REGION,
                )
            else:
                # Fall back to default AWS credentials / IAM role on EC2
                s3_client = boto3.client("s3", region_name=AWS_REGION)
            logger.info(f"S3 client initialized for region '{AWS_REGION}', bucket '{S3_BUCKET_NAME}'")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")


def handle_artifacts(
    job_id: str,
    local_video_path: Union[str, Path],
    local_srt_path: Optional[Union[str, Path]] = None,
) -> dict:
    """
    If USE_S3 is True: Uploads artifacts to S3, returns public S3 URLs, and cleans up local disk.
    If USE_S3 is False: Retains local files and returns local download route endpoints.
    """
    video_str = str(local_video_path) if local_video_path else None
    srt_str = str(local_srt_path) if local_srt_path else None

    if not USE_S3 or s3_client is None:
        logger.info(f"Local mode enabled (USE_S3=false). Preserving artifacts for job {job_id}.")
        return {
            "video_url": f"/download/{job_id}",
            "subtitles_url": f"/subtitles/{job_id}" if (srt_str and os.path.exists(srt_str)) else None,
        }

    urls = {}
    try:
        # 1. Upload Video
        if video_str and os.path.exists(video_str):
            video_key = f"videos/{job_id}.mp4"
            logger.info(f"Uploading {video_str} to s3://{S3_BUCKET_NAME}/{video_key}...")
            s3_client.upload_file(
                video_str,
                S3_BUCKET_NAME,
                video_key,
                ExtraArgs={"ContentType": "video/mp4"},
            )
            urls["video_url"] = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{video_key}"

        # 2. Upload Subtitles (if present)
        if srt_str and os.path.exists(srt_str):
            srt_key = f"subtitles/{job_id}.srt"
            logger.info(f"Uploading {srt_str} to s3://{S3_BUCKET_NAME}/{srt_key}...")
            s3_client.upload_file(
                srt_str,
                S3_BUCKET_NAME,
                srt_key,
                ExtraArgs={"ContentType": "text/plain; charset=utf-8"},
            )
            urls["subtitles_url"] = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{srt_key}"

    except (ClientError, Exception) as e:
        logger.error(f"S3 artifact upload failed for job {job_id}: {str(e)}")
        raise e
    finally:
        # Crucial for preventing EC2 disk saturation
        if video_str and os.path.exists(video_str):
            try:
                os.remove(video_str)
                logger.debug(f"Removed temporary local video: {video_str}")
            except Exception as ex:
                logger.warning(f"Could not remove local video {video_str}: {ex}")

        if srt_str and os.path.exists(srt_str):
            try:
                os.remove(srt_str)
                logger.debug(f"Removed temporary local subtitles: {srt_str}")
            except Exception as ex:
                logger.warning(f"Could not remove local subtitles {srt_str}: {ex}")

    return urls
