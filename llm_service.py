"""
Explain IQ — LLM Storyboard Service
===================================
Uses Google Gemini with native structured output to generate
a scene-by-scene storyboard for educational explainer videos.
Generates structured visual slide parameters and audio narration.
"""

import asyncio
import json
import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field
from google import genai

from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

# ── Pydantic Schemas ───────────────────────────────────────────

class SlideMetadata(BaseModel):
    """Parameters for a beautifully rendered educational slide card."""
    template: Literal["title_card", "text_bullet", "concept_card", "summary"] = Field(
        default="title_card",
        description="Slide template layout: 'title_card' (intro/outro), 'text_bullet' (key facts/list), 'concept_card' (core law/formula/quote), 'summary' (takeaway conclusion)"
    )
    title: str = Field(
        default="Key Concept",
        description="Title text displayed on the slide"
    )
    subtitle: Optional[str] = Field(
        default=None,
        description="Subtitle, category, or brief explanation"
    )
    bullet_points: Optional[list[str]] = Field(
        default=None,
        description="3-4 bullet points for text_bullet template"
    )
    key_text: Optional[str] = Field(
        default=None,
        description="Key formula, definition, equation, or highlighted statement for concept_card"
    )
    highlight_color: Optional[str] = Field(
        default="#38BDF8",
        description="Hex accent color (e.g. #38BDF8 cyan, #10B981 green, #F59E0B amber, #EC4899 pink, #8B5CF6 purple)"
    )


class ImageMetadata(BaseModel):
    """Parameters for an illustrative visual scene."""
    search_query: str = Field(
        description="Search query describing the visual scene or topic"
    )
    alt_text: str = Field(
        description="Accessible description of what the visual illustrates"
    )


class Scene(BaseModel):
    """A single scene in the storyboard."""
    scene_id: int = Field(description="Sequential scene number starting from 1")
    narration_text: str = Field(
        description="The voiceover narration for this scene (15-25 seconds of speech)"
    )
    visual_type: Literal["slide", "image", "manim"] = Field(
        default="slide",
        description="Visual type: 'slide' for structured educational graphic card, 'image' for illustrative scene"
    )
    slide_metadata: Optional[SlideMetadata] = Field(
        default=None,
        description="Parameters for slide scene"
    )
    manim_metadata: Optional[SlideMetadata] = Field(
        default=None,
        description="Backward compatibility field for slide metadata"
    )
    image_metadata: Optional[ImageMetadata] = Field(
        default=None,
        description="Parameters for image scene"
    )


class Storyboard(BaseModel):
    """Complete storyboard for an educational explainer video."""
    title: str = Field(description="Title of the educational video")
    scenes: list[Scene] = Field(
        description="Ordered list of 4-8 scenes making up the video"
    )


# ── System Prompt ──────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert educational video director and instructional designer.
Your task is to create a structured, engaging storyboard for a short (1-2 minute) educational explainer video.

RULES:
1. Create exactly 4 to 8 scenes.
2. The FIRST scene MUST have visual_type "slide" with template "title_card" to introduce the topic.
3. Alternate between "slide" and "image" visual types for variety and viewer engagement.
   - Include at least 2 "slide" scenes and at least 2 "image" scenes.
4. Each scene's narration_text should be 2 to 4 clear, spoken sentences (targeting 15-25 seconds of speech).
5. For "slide" scenes:
   - "title_card": Used for intro and outro. Provide an inspiring title and subtitle.
   - "text_bullet": Used for listing 3-4 key principles, components, or sequential steps.
   - "concept_card": Used for highlighting a fundamental law, core equation, or definition in key_text.
   - "summary": Used for the final review of takeaways.
6. For "image" scenes:
   - Provide a clear, descriptive search_query and meaningful alt_text.
7. The narration must flow smoothly from one scene to the next, like a top-tier science explainer.
8. Use highlight_color to create visual interest (#38BDF8 sky blue, #10B981 emerald, #F59E0B amber, #EC4899 pink, #8B5CF6 purple).
"""


# ── Storyboard Generation ─────────────────────────────────────

async def generate_storyboard(
    concept: str,
    target_audience: str = "high school students",
    duration_mode: str = "standard",
) -> Storyboard:
    """
    Generate a structured storyboard using Gemini with native structured output.

    Args:
        concept: The educational concept to explain (e.g., "Newton's Laws of Motion")
        target_audience: Target viewer demographic
        duration_mode: "quick" (3-4 scenes), "standard" (4-6 scenes), or "deep_dive" (6-8 scenes)

    Returns:
        A validated Storyboard instance with normalized scenes.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. "
            "Get one at https://aistudio.google.com/app/apikey and add it to your .env file."
        )

    client = genai.Client(api_key=GEMINI_API_KEY)

    scene_guide = {
        "quick": "Create exactly 3 to 4 concise scenes (targeting 45-60 seconds total video duration).",
        "standard": "Create exactly 4 to 6 engaging scenes (targeting 90-120 seconds total video duration).",
        "deep_dive": "Create 6 to 8 comprehensive scenes (targeting 3-4 minutes total video duration with in-depth explanations).",
    }.get(duration_mode, "Create 4 to 6 concise scenes.")

    user_prompt = (
        f"Create an engaging educational storyboard about: {concept}\n"
        f"Target audience: {target_audience}\n\n"
        f"{scene_guide}\n"
        f"Begin with a title card slide, follow with core concepts, bullet points, and real illustrative stock image scenes."
    )

    max_retries = 3
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Storyboard generation attempt {attempt}/{max_retries} for: {concept}")

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=GEMINI_MODEL,
                contents=user_prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "response_mime_type": "application/json",
                    "response_schema": Storyboard,
                },
            )

            storyboard = response.parsed

            if storyboard is None:
                raw_text = response.text
                logger.warning("response.parsed returned None, attempting manual JSON parse")
                storyboard = Storyboard.model_validate_json(raw_text)

            # Validate scene count (clamp between 4 and 8)
            if len(storyboard.scenes) > 8:
                storyboard.scenes = storyboard.scenes[:8]

            # Normalize scenes and ensure compatibility
            for i, scene in enumerate(storyboard.scenes):
                scene.scene_id = i + 1

                # Normalize visual_type: if 'manim' was selected, map to 'slide'
                if scene.visual_type == "manim":
                    scene.visual_type = "slide"

                # Link backward-compatible manim_metadata to slide_metadata
                if scene.slide_metadata is None and scene.manim_metadata is not None:
                    scene.slide_metadata = scene.manim_metadata

                # Ensure slide scenes have valid metadata
                if scene.visual_type == "slide" and scene.slide_metadata is None:
                    scene.slide_metadata = SlideMetadata(
                        template="title_card" if i == 0 else "text_bullet",
                        title=storyboard.title if i == 0 else f"Scene {scene.scene_id}",
                        subtitle=concept,
                        bullet_points=["Key principle", "Important application", "Summary takeaway"],
                    )

                # Ensure image scenes have valid metadata
                if scene.visual_type == "image" and scene.image_metadata is None:
                    scene.image_metadata = ImageMetadata(
                        search_query=concept,
                        alt_text=f"Scene {scene.scene_id}: {concept}",
                    )

            logger.info(
                f"Storyboard generated: '{storyboard.title}' with {len(storyboard.scenes)} scenes"
            )
            return storyboard

        except Exception as e:
            last_error = e
            logger.error(f"Attempt {attempt} failed: {e}")
            if attempt < max_retries:
                wait_time = 2 ** attempt
                logger.info(f"Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)

    raise RuntimeError(
        f"Failed to generate storyboard after {max_retries} attempts. Last error: {last_error}"
    )
