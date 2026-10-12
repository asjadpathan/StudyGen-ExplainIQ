"""
Explain IQ — Video Assembler
============================
Syncs visual slides and images with TTS audio and assembles the final .mp4 video
using MoviePy with cinematic Ken Burns motion, background audio ducking,
and isolated temporary audio rendering (zero root directory pollution).
Compatible with both MoviePy 1.x and 2.x.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import numpy as np
from PIL import Image

# Monkey-patch PIL.Image.ANTIALIAS for MoviePy 1.x compatibility with Pillow 10+
import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    setattr(PIL.Image, "ANTIALIAS", PIL.Image.Resampling.LANCZOS)

# Import MoviePy with backward-compatibility for 1.x and 2.x
try:
    from moviepy.editor import (
        VideoFileClip,
        VideoClip,
        ImageClip,
        AudioFileClip,
        CompositeVideoClip,
        CompositeAudioClip,
        concatenate_videoclips,
        concatenate_audioclips,
        vfx,
    )
    MOVIEPY_V2 = False
except ImportError:
    from moviepy import (
        VideoFileClip,
        VideoClip,
        ImageClip,
        AudioFileClip,
        CompositeVideoClip,
        CompositeAudioClip,
        concatenate_videoclips,
        concatenate_audioclips,
        vfx,
    )
    MOVIEPY_V2 = True

from config import VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS, TEMP_DIR, AUDIO_DIR

logger = logging.getLogger(__name__)


@dataclass
class SceneAssets:
    """Holds all file paths and metadata for a single assembled scene."""
    scene_id: int
    visual_path: Path           # .png from Slide/Image or .mp4
    audio_path: Path            # .mp3 from TTS
    audio_duration: float       # seconds
    visual_type: str            # "slide", "image", or "manim"


# ── Ken Burns Cinematic Motion Helper ──────────────────────────

def create_ken_burns_clip(
    image_path: Path,
    duration: float,
    width: int = VIDEO_WIDTH,
    height: int = VIDEO_HEIGHT,
    scene_id: int = 1,
) -> VideoClip:
    """
    Creates a dynamic clip with smooth camera drift (Ken Burns effect)
    using zero-copy NumPy array slicing for high encoding speed.
    """
    # 1.05x slightly oversized source for smooth drift window
    scale = 1.05
    target_w = int(width * scale)
    target_h = int(height * scale)

    with Image.open(image_path) as raw_img:
        base_img = raw_img.convert("RGB").resize((target_w, target_h), Image.Resampling.LANCZOS)
        img_arr = np.array(base_img)

    max_dx = max(0, target_w - width)
    max_dy = max(0, target_h - height)

    # Alternate drift directions between odd and even scenes for visual rhythm
    direction = scene_id % 3

    def make_frame(t: float) -> np.ndarray:
        p = min(1.0, max(0.0, t / max(duration, 0.01)))
        # Smooth cosine ease in/out
        ease = 0.5 - 0.5 * np.cos(np.pi * p)

        if direction == 0:
            # Zoom drift towards center
            x = int(ease * (max_dx // 2))
            y = int(ease * (max_dy // 2))
        elif direction == 1:
            # Slow pan left-to-right
            x = int((1.0 - ease) * max_dx)
            y = int(max_dy // 2)
        else:
            # Slow pan right-to-left
            x = int(ease * max_dx)
            y = int(ease * max_dy)

        # Clamp offsets
        x = max(0, min(max_dx, x))
        y = max(0, min(max_dy, y))
        return img_arr[y : y + height, x : x + width]

    return VideoClip(make_frame, duration=duration)


# ── Scene Clip Synchronization ─────────────────────────────────

def sync_scene_clip(
    visual_path: Path,
    audio_path: Path,
    target_duration: float,
    visual_type: str = "slide",
    scene_id: int = 1,
    enable_motion: bool = True,
) -> VideoClip:
    """
    Create a synchronized video clip from visual slide + voiceover audio.
    Ensures high-resolution, rock-solid video frames with matching audio track.
    """
    logger.info(
        f"Syncing scene {scene_id}: {visual_path.name} + {audio_path.name} → {target_duration:.1f}s"
    )

    audio = AudioFileClip(str(audio_path))
    target_duration = max(0.5, float(target_duration))
    is_video = str(visual_path).lower().endswith(".mp4")

    if is_video:
        if MOVIEPY_V2:
            video = VideoFileClip(str(visual_path))
            if video.duration < target_duration:
                frozen = video.to_ImageClip(t=max(0, video.duration - 0.1)).with_duration(target_duration - video.duration)
                video = concatenate_videoclips([video, frozen])
            elif video.duration > target_duration:
                video = video.subclipped(0, target_duration)
            video = video.resized((VIDEO_WIDTH, VIDEO_HEIGHT)).with_audio(audio).with_duration(target_duration)
        else:
            video = VideoFileClip(str(visual_path))
            if video.duration < target_duration:
                frozen = video.to_ImageClip(t=max(0, video.duration - 0.1)).set_duration(target_duration - video.duration)
                video = concatenate_videoclips([video, frozen])
            elif video.duration > target_duration:
                video = video.subclip(0, target_duration)
            video = video.resize((VIDEO_WIDTH, VIDEO_HEIGHT)).set_audio(audio).set_duration(target_duration)
    else:
        # Static image / slide: Apply Ken Burns cinematic motion if enabled
        if enable_motion:
            video = create_ken_burns_clip(
                image_path=visual_path,
                duration=target_duration,
                width=VIDEO_WIDTH,
                height=VIDEO_HEIGHT,
                scene_id=scene_id,
            )
        else:
            video = ImageClip(str(visual_path))
            if MOVIEPY_V2:
                video = video.with_duration(target_duration).resized((VIDEO_WIDTH, VIDEO_HEIGHT))
            else:
                video = video.set_duration(target_duration).resize((VIDEO_WIDTH, VIDEO_HEIGHT))

        # Attach audio to the video clip
        if MOVIEPY_V2:
            video = video.with_audio(audio).with_duration(target_duration)
        else:
            video = video.set_audio(audio).set_duration(target_duration)

    return video


# ── Final Video Assembly ───────────────────────────────────────

def assemble_final_video(
    scenes: List[SceneAssets],
    output_path: Path,
    include_music: bool = False,
    background_music_path: Optional[Path] = None,
    enable_motion: bool = True,
) -> Path:
    """
    Assemble all scene clips into the final educational video.
    Safely routes temporary audio files into TEMP_DIR to keep root clean.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Assembling {len(scenes)} scenes into final video: {output_path.name}")

    clips = []
    for scene in scenes:
        try:
            clip = sync_scene_clip(
                visual_path=scene.visual_path,
                audio_path=scene.audio_path,
                target_duration=scene.audio_duration,
                visual_type=scene.visual_type,
                scene_id=scene.scene_id,
                enable_motion=enable_motion,
            )
            clips.append(clip)
            logger.info(f"  Scene {scene.scene_id}: {scene.audio_duration:.1f}s ✓")
        except Exception as e:
            logger.error(f"  Scene {scene.scene_id} sync failed: {e}", exc_info=True)

    if not clips:
        raise RuntimeError("No scenes could be assembled into the final video")

    import gc
    gc.collect()

    # Use method="chain" for sequential concatenation (much lighter on RAM than "compose")
    try:
        final = concatenate_videoclips(clips, method="chain")
    except Exception:
        final = concatenate_videoclips(clips, method="compose")
    total_duration = sum(s.audio_duration for s in scenes)

    # Optional background music layering with audio ducking
    music_clip = None
    if include_music:
        candidate_music = background_music_path or (AUDIO_DIR / "ambient.mp3")
        if candidate_music.exists():
            try:
                bg = AudioFileClip(str(candidate_music))
                # Loop background music if shorter than video
                if bg.duration < total_duration:
                    repeats = int(total_duration // bg.duration) + 1
                    bg = concatenate_audioclips([bg] * repeats)
                
                # Trim to total duration
                if MOVIEPY_V2:
                    bg = bg.subclipped(0, total_duration)
                    # Duck volume to ~8%
                    if hasattr(bg, "with_volume_scaled"):
                        bg = bg.with_volume_scaled(0.08)
                    elif hasattr(vfx, "MultiplyVolume"):
                        bg = bg.with_effects([vfx.MultiplyVolume(0.08)])
                else:
                    bg = bg.subclip(0, total_duration).volumex(0.08)

                # Composite narration audio with ducked music
                current_audio = final.audio
                if current_audio is not None:
                    mixed_audio = CompositeAudioClip([current_audio, bg])
                    if MOVIEPY_V2:
                        final = final.with_audio(mixed_audio)
                    else:
                        final = final.set_audio(mixed_audio)
                    music_clip = bg
                    logger.info("Background music layered with audio ducking (-22 dB)")
            except Exception as e:
                logger.warning(f"Could not layer background music: {e}")

    # Isolated temporary audio file in TEMP_DIR to prevent root directory pollution
    temp_audio_file = TEMP_DIR / f"{output_path.stem}_temp_snd.m4a"

    try:
        logger.info(f"Writing output video: {output_path} (low-memory stream)")
        final.write_videofile(
            str(output_path),
            fps=VIDEO_FPS,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            temp_audiofile=str(temp_audio_file),
            remove_temp=True,
            logger=None,
            threads=1,
            ffmpeg_params=["-pix_fmt", "yuv420p"],
        )
    finally:
        # Guarantee cleanup of open file handles
        if music_clip is not None:
            try:
                music_clip.close()
            except Exception:
                pass
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass
        try:
            final.close()
        except Exception:
            pass
        # Clean up stray temp audio if still present
        if temp_audio_file.exists():
            try:
                temp_audio_file.unlink()
            except Exception:
                pass

    logger.info(f"Final video successfully generated: {output_path} ({total_duration:.1f}s)")
    return output_path
