"""
Explain IQ — Slide Generation Service
=====================================
Generates high-resolution (1920x1080) educational graphic slides
using Pillow with modern typography, gradients, glassmorphism cards,
and pixel-perfect alignment. Replaces heavy external dependencies
with fast, reliable, and beautiful native graphics.
"""

import logging
import os
import textwrap
from pathlib import Path
from typing import Optional, Union

from PIL import Image, ImageDraw, ImageFont

from config import VIDEO_WIDTH, VIDEO_HEIGHT, FONTS_DIR

logger = logging.getLogger(__name__)

# ── Color Palettes ─────────────────────────────────────────────

BG_DARK_THEMES = [
    ((11, 15, 25), (20, 27, 45), "#38BDF8"),      # Deep obsidian & slate navy (cyan accent)
    ((15, 23, 42), (30, 41, 59), "#818CF8"),      # Slate dark (indigo accent)
    ((10, 15, 30), (24, 18, 43), "#A78BFA"),      # Midnight violet
    ((13, 27, 30), (19, 42, 45), "#34D399"),      # Deep forest emerald
    ((26, 18, 26), (41, 23, 38), "#F472B6"),      # Rose dark
]


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex string (e.g., '#38BDF8') to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    try:
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return (56, 189, 248)


def _get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Load bundled font or standard system font with robust path discovery."""
    # 1. Bundled fonts in assets/fonts/
    bundled_names = ["Inter-Bold.ttf" if bold else "Inter-Regular.ttf", "font.ttf"]
    for b_name in bundled_names:
        p = FONTS_DIR / b_name
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                pass

    # 2. Windows and Linux standard font directories
    win_dir = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
    candidates = [
        # Full Windows Font paths
        win_dir / ("segoeuib.ttf" if bold else "segoeui.ttf"),
        win_dir / ("arialbd.ttf" if bold else "arial.ttf"),
        win_dir / ("calibrib.ttf" if bold else "calibri.ttf"),
        # Relative names
        "segoeuib.ttf" if bold else "segoeui.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
        "arial.ttf",
        "calibri.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]

    for cand in candidates:
        try:
            return ImageFont.truetype(str(cand), size)
        except (OSError, IOError):
            continue

    return ImageFont.load_default()


def _draw_gradient_background(
    img: Image.Image,
    top_color: tuple[int, int, int] = (11, 15, 25),
    bottom_color: tuple[int, int, int] = (20, 27, 45),
) -> None:
    """Draw a smooth vertical gradient on the canvas."""
    draw = ImageDraw.Draw(img)
    w, h = img.size
    for y in range(h):
        ratio = y / h
        r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
        g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
        b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def _draw_header_badge(
    draw: ImageDraw.Draw,
    badge_text: str,
    accent_rgb: tuple[int, int, int],
) -> None:
    """Draw a modern pill badge at the top center of the canvas."""
    font_badge = _get_font(20, bold=True)
    badge_text = badge_text.upper()

    bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    tw = bbox[2] - bbox[0]

    badge_w = tw + 36
    badge_h = 38
    badge_x = (VIDEO_WIDTH - badge_w) // 2
    badge_y = 48

    # Pill container
    draw.rounded_rectangle(
        [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
        radius=19,
        fill=(accent_rgb[0] // 5, accent_rgb[1] // 5, accent_rgb[2] // 5),
        outline=accent_rgb,
        width=2,
    )
    draw.text(
        (VIDEO_WIDTH // 2, badge_y + 8),
        badge_text,
        fill=accent_rgb,
        font=font_badge,
        anchor="ma",
        align="center",
    )


# ── Template 1: Title Card ────────────────────────────────────

def render_title_card(
    title: str,
    subtitle: Optional[str] = None,
    highlight_color: str = "#38BDF8",
    output_path: Optional[Path] = None,
) -> Image.Image:
    """Render a title card with prominent typography and modern card frame."""
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT))
    _draw_gradient_background(img, (11, 17, 32), (23, 27, 54))
    draw = ImageDraw.Draw(img)
    accent_rgb = _hex_to_rgb(highlight_color)

    _draw_header_badge(draw, "EDUCATIONAL EXPLAINER", accent_rgb)

    # Center card container
    card_x1, card_y1 = 180, 150
    card_x2, card_y2 = VIDEO_WIDTH - 180, VIDEO_HEIGHT - 130
    draw.rounded_rectangle(
        [card_x1, card_y1, card_x2, card_y2],
        radius=28,
        fill=(17, 24, 39),
        outline=(55, 65, 81),
        width=2,
    )

    # Accent top glowing stripe
    draw.rounded_rectangle(
        [card_x1 + 60, card_y1 + 4, card_x2 - 60, card_y1 + 10],
        radius=3,
        fill=accent_rgb,
    )

    # Typography
    font_title = _get_font(56, bold=True)
    font_sub = _get_font(30)

    # Wrap title cleanly
    title_wrapped = textwrap.fill(title, width=34)

    # Measure wrapped title height
    tbox = draw.textbbox((0, 0), title_wrapped, font=font_title, align="center")
    th = tbox[3] - tbox[1]

    # Calculate vertical balance
    card_center_y = (card_y1 + card_y2) // 2
    if subtitle:
        title_y = card_center_y - (th // 2) - 60
    else:
        title_y = card_center_y - (th // 2)

    # Title shadow + text perfectly centered horizontally
    draw.text((VIDEO_WIDTH // 2 + 2, title_y + 2), title_wrapped, fill=(0, 0, 0), font=font_title, anchor="ma", align="center")
    draw.text((VIDEO_WIDTH // 2, title_y), title_wrapped, fill=(255, 255, 255), font=font_title, anchor="ma", align="center")

    # Divider and Subtitle
    if subtitle:
        div_y = title_y + th + 36
        draw.line(
            [(VIDEO_WIDTH // 2 - 120, div_y), (VIDEO_WIDTH // 2 + 120, div_y)],
            fill=accent_rgb,
            width=4,
        )

        sub_wrapped = textwrap.fill(subtitle, width=54)
        draw.text(
            (VIDEO_WIDTH // 2, div_y + 28),
            sub_wrapped,
            fill=(203, 213, 225),
            font=font_sub,
            anchor="ma",
            align="center",
        )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG")
    return img


# ── Template 2: Structured Bullet List ────────────────────────

def render_bullet_slide(
    title: str,
    bullet_points: list[str],
    highlight_color: str = "#38BDF8",
    output_path: Optional[Path] = None,
) -> Image.Image:
    """Render a structured bullet list with individually aligned row cards."""
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT))
    _draw_gradient_background(img, (13, 19, 33), (22, 30, 49))
    draw = ImageDraw.Draw(img)
    accent_rgb = _hex_to_rgb(highlight_color)

    _draw_header_badge(draw, "KEY CONCEPTS", accent_rgb)

    # Slide Title at Top
    font_head = _get_font(44, bold=True)
    head_wrapped = textwrap.fill(title, width=48)
    draw.text((140, 110), head_wrapped, fill=(255, 255, 255), font=font_head)

    # Accent underline
    tbox = draw.textbbox((140, 110), head_wrapped, font=font_head)
    under_y = tbox[3] + 14
    draw.line([(140, under_y), (360, under_y)], fill=accent_rgb, width=4)

    # Bullets container
    card_x1 = 140
    card_x2 = VIDEO_WIDTH - 140
    card_y1 = under_y + 30
    card_y2 = VIDEO_HEIGHT - 70

    draw.rounded_rectangle(
        [card_x1, card_y1, card_x2, card_y2],
        radius=24,
        fill=(17, 24, 39),
        outline=(55, 65, 81),
        width=2,
    )

    bullets = (bullet_points or [])[:4]
    if not bullets:
        bullets = ["Core principle overview", "Practical application", "Key takeaway"]

    num_items = len(bullets)
    font_bullet = _get_font(28)
    font_num = _get_font(22, bold=True)

    # Row sizing and vertical centering
    row_h = 100 if num_items <= 3 else 88
    row_gap = 22
    total_rows_h = (num_items * row_h) + ((num_items - 1) * row_gap)
    start_y = card_y1 + (card_y2 - card_y1 - total_rows_h) // 2

    row_x1 = card_x1 + 36
    row_x2 = card_x2 - 36

    for i, bullet in enumerate(bullets):
        curr_y = start_y + i * (row_h + row_gap)

        # Individual pill row card
        draw.rounded_rectangle(
            [row_x1, curr_y, row_x2, curr_y + row_h],
            radius=16,
            fill=(24, 32, 47),
            outline=(45, 55, 72),
            width=1,
        )

        # Number circle badge vertically centered in row
        badge_r = 22
        badge_cx = row_x1 + 45
        badge_cy = curr_y + (row_h // 2)

        draw.ellipse(
            [badge_cx - badge_r, badge_cy - badge_r, badge_cx + badge_r, badge_cy + badge_r],
            fill=(accent_rgb[0] // 5, accent_rgb[1] // 5, accent_rgb[2] // 5),
            outline=accent_rgb,
            width=2,
        )

        num_str = f"{i + 1:02d}"
        draw.text((badge_cx, badge_cy), num_str, fill=accent_rgb, font=font_num, anchor="mm")

        # Bullet text vertically centered in row
        b_wrapped = textwrap.fill(bullet, width=62)
        text_x = row_x1 + 90
        draw.text((text_x, badge_cy), b_wrapped, fill=(241, 245, 249), font=font_bullet, anchor="lm")

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG")
    return img


# ── Template 3: Concept / Formula Card ────────────────────────

def render_concept_card(
    title: str,
    key_text: str,
    subtitle: Optional[str] = None,
    highlight_color: str = "#F59E0B",
    output_path: Optional[Path] = None,
) -> Image.Image:
    """Render a highlighted focus card with balanced center typography."""
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT))
    _draw_gradient_background(img, (14, 18, 29), (28, 23, 36))
    draw = ImageDraw.Draw(img)
    accent_rgb = _hex_to_rgb(highlight_color)

    _draw_header_badge(draw, "CORE PRINCIPLE", accent_rgb)

    # Header title
    font_title = _get_font(42, bold=True)
    title_wrapped = textwrap.fill(title, width=44)
    draw.text((VIDEO_WIDTH // 2, 115), title_wrapped, fill=(255, 255, 255), font=font_title, anchor="ma", align="center")

    # Center callout card
    card_x1, card_y1 = 180, 210
    card_x2, card_y2 = VIDEO_WIDTH - 180, VIDEO_HEIGHT - 120
    draw.rounded_rectangle(
        [card_x1, card_y1, card_x2, card_y2],
        radius=28,
        fill=(19, 24, 38),
        outline=accent_rgb,
        width=3,
    )

    card_center_y = (card_y1 + card_y2) // 2

    # Highlighted key text
    font_key = _get_font(50, bold=True)
    key_wrapped = textwrap.fill(key_text, width=36)

    kbox = draw.textbbox((0, 0), key_wrapped, font=font_key, align="center")
    kh = kbox[3] - kbox[1]

    key_y = card_center_y - (kh // 2) - (35 if subtitle else 0)

    # Glowing colored key text centered with anchor="ma"
    draw.text((VIDEO_WIDTH // 2 + 2, key_y + 2), key_wrapped, fill=(0, 0, 0), font=font_key, anchor="ma", align="center")
    draw.text((VIDEO_WIDTH // 2, key_y), key_wrapped, fill=accent_rgb, font=font_key, anchor="ma", align="center")

    # Subtitle explanation below key text
    if subtitle:
        font_sub = _get_font(28)
        sub_wrapped = textwrap.fill(subtitle, width=54)
        sub_y = key_y + kh + 40
        draw.text(
            (VIDEO_WIDTH // 2, sub_y),
            sub_wrapped,
            fill=(203, 213, 225),
            font=font_sub,
            anchor="ma",
            align="center",
        )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG")
    return img


# ── Unified Slide Dispatcher ──────────────────────────────────

def render_slide(
    template_name: str,
    config_data: dict,
    output_dir: Path,
    scene_id: int,
) -> Path:
    """
    Render an educational slide image based on template name and parameters.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"scene_{scene_id}_slide.png"

    title = config_data.get("title", f"Scene {scene_id}")
    color = config_data.get("highlight_color", "#38BDF8")
    subtitle = config_data.get("subtitle", "")
    bullets = config_data.get("bullet_points", [])
    key_text = config_data.get("equation") or config_data.get("key_text") or title

    logger.info(f"Rendering slide scene {scene_id}: template={template_name}, title='{title}'")

    if template_name in ("title_card", "intro", "outro"):
        render_title_card(
            title=title,
            subtitle=subtitle or (bullets[0] if bullets else ""),
            highlight_color=color,
            output_path=output_path,
        )
    elif template_name in ("text_bullet", "bullets", "summary"):
        render_bullet_slide(
            title=title,
            bullet_points=bullets or [key_text],
            highlight_color=color,
            output_path=output_path,
        )
    elif template_name in ("equation", "concept_card", "callout"):
        render_concept_card(
            title=title,
            key_text=key_text,
            subtitle=subtitle,
            highlight_color=color,
            output_path=output_path,
        )
    else:
        render_bullet_slide(
            title=title,
            bullet_points=bullets or [key_text],
            highlight_color=color,
            output_path=output_path,
        )

    return output_path
