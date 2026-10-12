"""
Explain IQ — Template Renderer (Manim Replacement)
=================================================
Provides backward-compatible slide rendering for the video generation pipeline.
Redirects former Manim templates to native high-res slide rendering via slide_service.
"""

import logging
from pathlib import Path

from slide_service import render_slide

logger = logging.getLogger(__name__)


def render_manim_scene(
    template_name: str,
    config_data: dict,
    output_dir: Path,
    scene_id: int,
) -> Path:
    """
    Backward-compatible entry point for rendering visual scenes.
    Delegates directly to render_slide without external Manim dependencies.
    """
    logger.info(f"Rendering scene {scene_id} via native slide engine (template: {template_name})")
    return render_slide(
        template_name=template_name,
        config_data=config_data,
        output_dir=output_dir,
        scene_id=scene_id,
    )
