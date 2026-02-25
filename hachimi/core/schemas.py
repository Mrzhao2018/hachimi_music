"""Pydantic data models for the Hachimi Music pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────

class MusicStyle(str, Enum):
    CLASSICAL = "classical"
    POP = "pop"
    JAZZ = "jazz"
    ROCK = "rock"
    ELECTRONIC = "electronic"
    FOLK = "folk"
    BLUES = "blues"
    LATIN = "latin"
    AMBIENT = "ambient"
    CINEMATIC = "cinematic"


class TaskStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"       # AI is composing the score
    CONVERTING = "converting"       # ABC → MIDI conversion
    RENDERING = "rendering"         # MIDI → Audio synthesis
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    FAILED = "failed"


class OutputFormat(str, Enum):
    WAV = "wav"
    MP3 = "mp3"


# ── Request / Input Models ────────────────────────────────────────────────

class VoicePart(BaseModel):
    """A single voice/instrument part specification."""
    name: str = Field(..., description="Voice part name, e.g. 'melody', 'bass', 'harmony'")
    instrument: str = Field(..., description="Instrument name, e.g. 'piano', 'violin', 'flute'")


class MusicRequest(BaseModel):
    """User request to generate a piece of music."""
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural language description of the desired music",
    )
    style: MusicStyle = Field(default=MusicStyle.CLASSICAL, description="Musical style")
    key: str = Field(default="C", description="Musical key, e.g. 'C', 'Am', 'Eb', 'F#m'")
    time_signature: str = Field(default="4/4", description="Time signature, e.g. '4/4', '3/4', '6/8'")
    tempo: int = Field(default=120, ge=30, le=300, description="Tempo in BPM")
    measures: int = Field(default=16, ge=4, le=64, description="Number of measures to generate")
    instruments: list[str] = Field(
        default_factory=lambda: ["piano"],
        description="List of instruments to use",
    )
    output_format: OutputFormat = Field(default=OutputFormat.MP3, description="Output audio format")


# ── AI Generation Result ──────────────────────────────────────────────────

class InstrumentAssignment(BaseModel):
    """Maps a voice part to a specific instrument."""
    voice_id: str = Field(..., description="Voice identifier in ABC, e.g. '1', '2'")
    voice_name: str = Field(..., description="Voice part name, e.g. 'melody'")
    instrument: str = Field(..., description="Instrument name, e.g. 'Acoustic Grand Piano'")
    gm_program: Optional[int] = Field(
        default=None, ge=0, le=127,
        description="General MIDI program number (0-127)",
    )
    midi_channel: Optional[int] = Field(
        default=None, ge=0, le=15,
        description="MIDI channel (0-15, channel 9 = drums)",
    )


class ScoreResult(BaseModel):
    """Result from AI music generation."""
    abc_notation: str = Field(..., description="Generated ABC notation score")
    title: str = Field(default="Untitled", description="Title of the piece")
    composer: str = Field(default="Hachimi AI", description="Composer attribution")
    key: str = Field(..., description="Musical key of the piece")
    time_signature: str = Field(..., description="Time signature")
    tempo: int = Field(..., description="Tempo in BPM")
    instruments: list[InstrumentAssignment] = Field(
        default_factory=list,
        description="Instrument assignments for each voice",
    )
    style: str = Field(default="classical", description="Musical style")
    description: str = Field(default="", description="AI's description of the generated piece")


# ── Pipeline Output ───────────────────────────────────────────────────────

class AudioResult(BaseModel):
    """Final output of the music generation pipeline."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.now)

    # Score data
    score: Optional[ScoreResult] = None
    abc_notation: Optional[str] = None

    # File paths
    midi_path: Optional[str] = None
    audio_path: Optional[str] = None

    # Metadata
    duration_seconds: Optional[float] = None
    sample_rate: int = 44100
    output_format: OutputFormat = OutputFormat.MP3

    # Error info
    error_message: Optional[str] = None


# ── Task Tracking ─────────────────────────────────────────────────────────

class TaskInfo(BaseModel):
    """Task status info for the API."""
    task_id: str
    status: TaskStatus
    created_at: datetime
    progress_message: str = ""
    result: Optional[AudioResult] = None
