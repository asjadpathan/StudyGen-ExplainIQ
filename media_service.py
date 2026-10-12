"""
Explain IQ — Media Services
==========================
TTS audio generation via edge-tts (with word-level subtitle capture)
and real stock image fetching from Pexels API and Wikimedia Commons API.
No AI image generation — fetches real, high-resolution photography and graphics.
"""

import asyncio
import json
import logging
import os
import re
import ssl
import textwrap
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple, List

import edge_tts
from mutagen.mp3 import MP3
from PIL import Image, ImageDraw, ImageFont

from config import TTS_VOICE, VIDEO_WIDTH, VIDEO_HEIGHT, PEXELS_API_KEY, FONTS_DIR

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _create_ssl_context():
    """Create a permissive SSL context for Windows compatibility."""
    ctx = ssl.create_default_context()
    try:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    except Exception:
        pass
    return ctx


# ── TTS Audio & Subtitle Generation ────────────────────────────

async def generate_tts(
    text: str,
    output_path: Path,
    voice: str = TTS_VOICE,
    srt_output_path: Optional[Path] = None,
) -> Tuple[Path, float]:
    """
    Generate TTS audio for narration text using Microsoft Edge neural voices.
    Also extracts word boundary timestamps for .srt subtitle generation.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Generating TTS: {len(text)} chars → {output_path.name}")

    communicate = edge_tts.Communicate(text, voice)
    sub_maker = getattr(edge_tts, "SubMaker", None)() if hasattr(edge_tts, "SubMaker") else None

    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary" and sub_maker is not None:
                sub_maker.feed(chunk)

    if srt_output_path and sub_maker is not None:
        try:
            srt_content = sub_maker.get_srt()
            if srt_content:
                srt_output_path.parent.mkdir(parents=True, exist_ok=True)
                srt_output_path.write_text(srt_content, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not generate scene SRT: {e}")

    audio = MP3(str(output_path))
    duration = float(audio.info.length)

    logger.info(f"TTS generated: {output_path.name} ({duration:.1f}s)")
    return output_path, duration


# ── Real Stock Image Fetcher ───────────────────────────────────

def _sanitize_query_candidates(raw_query: str) -> List[str]:
    """
    Extract progressive clean search queries from descriptive prompts.
    Example: 'Diagram illustrating Newton third law with action reaction' ->
    ['Newton third law action reaction', 'Newton third law', 'Newton motion']
    """
    # Remove filler phrases
    cleaned = re.sub(
        r"\b(illustration of|diagram of|photo of|picture of|showing|depicting|with|a|an|the|in|and|of|for|scene|image)\b",
        " ",
        raw_query,
        flags=re.IGNORECASE,
    )
    # Remove punctuation
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    words = [w.strip() for w in cleaned.split() if len(w.strip()) > 2]

    candidates = []
    if words:
        # 1. First 4-5 core keywords
        candidates.append(" ".join(words[:5]))
        # 2. First 2-3 keywords
        if len(words) > 2:
            candidates.append(" ".join(words[:3]))
        # 3. Top 2 keywords
        candidates.append(" ".join(words[:2]))

    # Deduplicate while preserving order
    unique_candidates = []
    for c in candidates:
        if c and c not in unique_candidates:
            unique_candidates.append(c)

    return unique_candidates or [raw_query]


def _fetch_from_pexels(query: str, api_key: str) -> Optional[bytes]:
    """Search and download a high-res landscape image from Pexels."""
    encoded_query = urllib.parse.quote(query)
    url = f"https://api.pexels.com/v1/search?query={encoded_query}&per_page=3&orientation=landscape"
    req = urllib.request.Request(
        url,
        headers={"Authorization": api_key, "User-Agent": USER_AGENT},
    )
    ctx = _create_ssl_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            photos = data.get("photos", [])
            if photos:
                img_url = photos[0].get("src", {}).get("large2x") or photos[0].get("src", {}).get("large")
                if img_url:
                    img_req = urllib.request.Request(img_url, headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(img_req, context=ctx, timeout=15) as img_resp:
                        return img_resp.read()
    except Exception as e:
        logger.warning(f"Pexels fetch failed for '{query}': {e}")
    return None


def _fetch_from_wikimedia(query: str) -> Optional[bytes]:
    """
    Search and download a free high-res image from Wikimedia Commons File namespace (gsrnamespace=6).
    Uses iiurlwidth=1920 to get instant pre-rendered 1080p thumbnails.
    """
    encoded_query = urllib.parse.quote(query)
    search_url = (
        "https://commons.wikimedia.org/w/api.php?action=query&generator=search"
        f"&gsrsearch={encoded_query}&gsrnamespace=6&gsrlimit=6"
        "&prop=imageinfo&iiprop=url|mime|size&iiurlwidth=1920&format=json"
    )
    req = urllib.request.Request(search_url, headers={"User-Agent": USER_AGENT})
    ctx = _create_ssl_context()

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})

            candidate_urls = []
            for page in pages.values():
                imageinfo = page.get("imageinfo", [])
                if not imageinfo:
                    continue
                info = imageinfo[0]
                mime = str(info.get("mime", "")).lower()
                thumb_url = info.get("thumburl") or info.get("url")

                # Filter out video/pdf formats
                if any(ext in str(thumb_url).lower() for ext in (".ogv", ".pdf", ".webm", ".ogg")):
                    continue
                if mime in ("application/pdf", "video/ogg", "video/webm"):
                    continue

                if thumb_url:
                    candidate_urls.append(thumb_url)

            # Download first valid candidate
            for img_url in candidate_urls[:3]:
                try:
                    img_req = urllib.request.Request(img_url, headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(img_req, context=ctx, timeout=15) as img_resp:
                        img_bytes = img_resp.read()
                        # Verify PIL can open it
                        with Image.open(BytesIO(img_bytes)) as test_img:
                            if test_img.size[0] > 100:
                                return img_bytes
                except Exception as inner_e:
                    logger.debug(f"Candidate {img_url} download error: {inner_e}")
                    continue

    except Exception as e:
        logger.warning(f"Wikimedia fetch failed for '{query}': {e}")
    return None


def _get_caption_font(size: int = 28) -> ImageFont.ImageFont:
    """Load clean caption font."""
    win_dir = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
    for cand in [FONTS_DIR / "Inter-Bold.ttf", win_dir / "segoeuib.ttf", win_dir / "arialbd.ttf", "arial.ttf"]:
        try:
            return ImageFont.truetype(str(cand), size)
        except Exception:
            continue
    return ImageFont.load_default()


def _process_and_save_image(
    raw_data: bytes,
    output_path: Path,
    alt_text: str = "",
    target_width: int = VIDEO_WIDTH,
    target_height: int = VIDEO_HEIGHT,
) -> None:
    """Center-crop and resize downloaded image with sleek glassmorphism caption badge."""
    with Image.open(BytesIO(raw_data)) as img:
        img = img.convert("RGB")
        src_w, src_h = img.size

        # Center-crop without distortion
        target_aspect = target_width / target_height
        src_aspect = src_w / src_h

        if src_aspect > target_aspect:
            new_w = int(src_h * target_aspect)
            offset = (src_w - new_w) // 2
            crop_box = (offset, 0, offset + new_w, src_h)
        else:
            new_h = int(src_w / target_aspect)
            offset = (src_h - new_h) // 2
            crop_box = (0, offset, src_w, offset + new_h)

        cropped = img.crop(crop_box).resize((target_width, target_height), Image.Resampling.LANCZOS)

        # Elegant glassmorphism caption pill at bottom center
        if alt_text and len(alt_text.strip()) > 2:
            caption_font = _get_caption_font(28)
            wrapped_caption = textwrap.fill(alt_text.strip(), width=68)

            dummy_draw = ImageDraw.Draw(cropped)
            bbox = dummy_draw.textbbox((0, 0), wrapped_caption, font=caption_font, align="center")
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            pill_w = min(target_width - 200, max(text_w + 64, 480))
            pill_h = text_h + 36
            pill_x1 = (target_width - pill_w) // 2
            pill_y1 = target_height - pill_h - 48
            pill_x2 = pill_x1 + pill_w
            pill_y2 = pill_y1 + pill_h

            overlay = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
            odraw = ImageDraw.Draw(overlay)

            # Dark translucent card with subtle glow outline
            odraw.rounded_rectangle(
                [pill_x1, pill_y1, pill_x2, pill_y2],
                radius=18,
                fill=(15, 23, 42, 220),
                outline=(56, 189, 248, 180),
                width=2,
            )

            # Centered caption text
            text_cy = (pill_y1 + pill_y2) // 2
            odraw.text(
                (target_width // 2, text_cy),
                wrapped_caption,
                fill=(255, 255, 255, 245),
                font=caption_font,
                anchor="mm",
                align="center",
            )

            cropped = Image.alpha_composite(cropped.convert("RGBA"), overlay).convert("RGB")

        cropped.save(output_path, "PNG")


def _generate_fallback_graphic(
    search_query: str,
    alt_text: str,
    output_path: Path,
) -> None:
    """Fallback graphic with balanced typography."""
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), (15, 23, 42))
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([180, 150, VIDEO_WIDTH - 180, VIDEO_HEIGHT - 150], radius=28, fill=(22, 30, 49), outline=(56, 189, 248), width=3)

    font_main = _get_caption_font(48)
    font_sub = _get_caption_font(28)

    wrapped_q = textwrap.fill(search_query, width=38)
    draw.text((VIDEO_WIDTH // 2, 440), wrapped_q, fill=(255, 255, 255), font=font_main, anchor="ma", align="center")

    if alt_text:
        wrapped_alt = textwrap.fill(alt_text, width=54)
        draw.text((VIDEO_WIDTH // 2, 580), wrapped_alt, fill=(148, 163, 184), font=font_sub, anchor="ma", align="center")

    img.save(output_path, "PNG")


async def fetch_stock_image(
    search_query: str,
    output_path: Path,
    alt_text: str = "",
) -> Path:
    """
    Fetch a real stock image matching the search query.
    1. Tries Pexels API if PEXELS_API_KEY is configured.
    2. Falls back to Wikimedia Commons API (no key required) with progressive keyword simplification.
    3. Falls back to styled graphic card if all network sources fail.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Fetching real stock image for: '{search_query}'")

    raw_data: Optional[bytes] = None
    query_candidates = _sanitize_query_candidates(search_query)

    # Step 1: Try Pexels if API key is provided
    if PEXELS_API_KEY:
        for candidate in query_candidates:
            raw_data = await asyncio.to_thread(_fetch_from_pexels, candidate, PEXELS_API_KEY)
            if raw_data:
                break

    # Step 2: Try Wikimedia Commons with candidate queries
    if not raw_data:
        for candidate in query_candidates:
            logger.info(f"Searching Wikimedia Commons for: '{candidate}'")
            raw_data = await asyncio.to_thread(_fetch_from_wikimedia, candidate)
            if raw_data:
                logger.info(f"Found real stock image on Wikimedia for '{candidate}'")
                break

    # Step 3: Process downloaded image or fallback
    if raw_data:
        try:
            await asyncio.to_thread(_process_and_save_image, raw_data, output_path, alt_text)
            logger.info(f"Real stock image saved: {output_path.name}")
            return output_path
        except Exception as e:
            logger.warning(f"Error processing image data: {e}")

    # Fallback graphic if network completely fails
    logger.warning(f"All image fetches failed for '{search_query}', using styled fallback")
    await asyncio.to_thread(_generate_fallback_graphic, search_query, alt_text, output_path)
    return output_path
