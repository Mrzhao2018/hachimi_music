"""Core music generation pipeline: orchestrates the full prompt → audio flow."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from hachimi.conversion.abc_to_midi import abc_to_midi, get_midi_duration
from hachimi.core.config import AppConfig, get_config
from hachimi.core.schemas import (
    AudioResult,
    MusicRequest,
    OutputFormat,
    ScoreResult,
    TaskStatus,
)
from hachimi.generation.llm_generator import LLMGenerator
from hachimi.synthesis.fluidsynth_renderer import FluidSynthRenderer
from hachimi.synthesis.postprocess import PostProcessor

logger = logging.getLogger(__name__)


class MusicPipeline:
    """
    End-to-end music generation pipeline.

    Flow: User Prompt → LLM → ABC notation → MIDI → FluidSynth → WAV → Post-process → MP3
    Supports checkpoint/retry: can resume from any stage.
    """

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or get_config()
        self.generator = LLMGenerator(self.config)
        self.renderer = FluidSynthRenderer(self.config)
        self.postprocessor = PostProcessor(self.config)

    def generate(
        self,
        request: MusicRequest,
        task_id: Optional[str] = None,
        progress_callback: Optional[callable] = None,
        resume_from: Optional[str] = None,
        existing_score: Optional[ScoreResult] = None,
        existing_midi: Optional[str] = None,
        existing_wav: Optional[str] = None,
        project_manager=None,
        project_id: Optional[str] = None,
    ) -> AudioResult:
        """
        Generate a complete piece of music from a natural language description.

        Args:
            request: The music generation request.
            task_id: Optional task ID for tracking.
            progress_callback: Optional callback(status, message) for progress updates.
            resume_from: Stage to resume from: 'generating', 'converting', 'rendering', 'postprocessing'
            existing_score: Pre-existing score (for retry from converting+)
            existing_midi: Pre-existing MIDI path (for retry from rendering+)
            existing_wav: Pre-existing WAV path (for retry from postprocessing)
            project_manager: Optional ProjectManager to save checkpoints
            project_id: Optional project ID for checkpoint saving
        """
        task_id = task_id or str(uuid.uuid4())
        output_dir = self.config.get_output_dir()

        result = AudioResult(
            task_id=task_id,
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
            output_format=request.output_format,
        )

        def _update(status: TaskStatus, message: str = ""):
            result.status = status
            logger.info("[%s] %s: %s", task_id[:8], status.value, message)
            if progress_callback:
                progress_callback(status, message)

        def _save_checkpoint(stage: str, **kwargs):
            if project_manager and project_id:
                try:
                    project_manager.update_checkpoint(project_id, stage, **kwargs)
                except Exception as e:
                    logger.warning("Failed to save checkpoint: %s", e)

        # Determine starting stage
        stages = ["generating", "converting", "rendering", "postprocessing"]
        start_idx = 0
        if resume_from and resume_from in stages:
            start_idx = stages.index(resume_from)
            logger.info("Resuming pipeline from stage: %s", resume_from)

        score_result = existing_score
        midi_path = Path(existing_midi) if existing_midi else None
        wav_path = Path(existing_wav) if existing_wav else None

        try:
            # ── Step 1: AI Generate Score ──────────────────────────────
            if start_idx <= 0:
                _update(TaskStatus.GENERATING, "AI is composing the music score...")
                score_result = self.generator.compose(request)
                result.score = score_result
                result.abc_notation = score_result.abc_notation
                _save_checkpoint(
                    "generated",
                    abc_notation=score_result.abc_notation,
                )
                logger.info("Generated score: %s (%d instruments)",
                            score_result.title, len(score_result.instruments))
            else:
                if score_result:
                    result.score = score_result
                    result.abc_notation = score_result.abc_notation

            # ── Step 2: ABC → MIDI ────────────────────────────────────
            if start_idx <= 1:
                if not score_result:
                    raise RuntimeError("No score available for MIDI conversion")
                _update(TaskStatus.CONVERTING, "Converting ABC notation to MIDI...")
                midi_path = output_dir / f"{task_id}.mid"
                midi_path = abc_to_midi(score_result, output_path=midi_path)
                result.midi_path = str(midi_path)
                _save_checkpoint("converted", midi_path=str(midi_path))

                try:
                    result.duration_seconds = get_midi_duration(midi_path)
                    logger.info("MIDI duration: %.1f seconds", result.duration_seconds)
                except Exception as e:
                    logger.warning("Could not determine MIDI duration: %s", e)
            else:
                if midi_path:
                    result.midi_path = str(midi_path)

            # ── Step 3: MIDI → WAV ────────────────────────────────────
            if start_idx <= 2:
                if not midi_path or not midi_path.exists():
                    raise RuntimeError("No MIDI file available for rendering")
                _update(TaskStatus.RENDERING, "Rendering MIDI to audio with SoundFont...")
                wav_path = output_dir / f"{task_id}.wav"
                wav_path = self.renderer.render(midi_path, output_path=wav_path)
                _save_checkpoint("rendered", wav_path=str(wav_path))
            else:
                pass  # wav_path already set

            # ── Step 4: Post-processing ───────────────────────────────
            if start_idx <= 3:
                if not wav_path or not wav_path.exists():
                    raise RuntimeError("No WAV file available for post-processing")
                _update(TaskStatus.POSTPROCESSING, "Applying audio effects and converting...")
                if request.output_format == OutputFormat.MP3:
                    audio_path = output_dir / f"{task_id}.mp3"
                    audio_path = self.postprocessor.apply(
                        wav_path, output_path=audio_path, output_format="mp3"
                    )
                else:
                    audio_path = self.postprocessor.apply(
                        wav_path, output_path=wav_path, output_format="wav"
                    )

                result.audio_path = str(audio_path)
                _save_checkpoint("postprocessed", audio_path=str(audio_path))

            # ── Done ──────────────────────────────────────────────────
            title = score_result.title if score_result else "Music"
            _update(TaskStatus.COMPLETED, f"Music generated: {title}")
            return result

        except Exception as e:
            result.status = TaskStatus.FAILED
            result.error_message = str(e)
            # Save checkpoint with error info
            failed_stage = stages[start_idx] if start_idx < len(stages) else "unknown"
            if project_manager:
                _save_checkpoint(
                    "none",
                    error_message=str(e),
                    error_stage=failed_stage,
                )
            logger.error("Pipeline failed at %s: %s", failed_stage, e, exc_info=True)
            return result
