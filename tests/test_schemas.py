"""Tests for schemas validation."""

import pytest
from hachimi.core.schemas import (
    AudioResult,
    InstrumentAssignment,
    MusicRequest,
    MusicStyle,
    OutputFormat,
    ScoreResult,
    TaskStatus,
)


class TestMusicRequest:
    def test_defaults(self):
        req = MusicRequest(prompt="a simple melody")
        assert req.style == MusicStyle.CLASSICAL
        assert req.key == "C"
        assert req.time_signature == "4/4"
        assert req.tempo == 120
        assert req.measures == 16
        assert req.instruments == ["piano"]
        assert req.output_format == OutputFormat.MP3

    def test_custom_values(self):
        req = MusicRequest(
            prompt="jazz piano",
            style=MusicStyle.JAZZ,
            key="Bb",
            tempo=140,
            instruments=["piano", "bass", "drums"],
        )
        assert req.style == MusicStyle.JAZZ
        assert req.key == "Bb"
        assert req.tempo == 140
        assert len(req.instruments) == 3

    def test_tempo_bounds(self):
        with pytest.raises(Exception):
            MusicRequest(prompt="test", tempo=10)  # Below min
        with pytest.raises(Exception):
            MusicRequest(prompt="test", tempo=500)  # Above max

    def test_empty_prompt_rejected(self):
        with pytest.raises(Exception):
            MusicRequest(prompt="")


class TestScoreResult:
    def test_basic(self):
        score = ScoreResult(
            abc_notation="X:1\nT:Test\nK:C\nCDEF|",
            key="C",
            time_signature="4/4",
            tempo=120,
        )
        assert score.title == "Untitled"
        assert score.composer == "Hachimi AI"

    def test_with_instruments(self):
        score = ScoreResult(
            abc_notation="X:1\nK:C\nCDEF|",
            key="C",
            time_signature="4/4",
            tempo=120,
            instruments=[
                InstrumentAssignment(
                    voice_id="1",
                    voice_name="melody",
                    instrument="Acoustic Grand Piano",
                    gm_program=0,
                ),
            ],
        )
        assert len(score.instruments) == 1
        assert score.instruments[0].gm_program == 0


class TestAudioResult:
    def test_default_status(self):
        result = AudioResult()
        assert result.status == TaskStatus.PENDING
        assert result.task_id  # Should have UUID
        assert result.created_at

    def test_task_id_unique(self):
        r1 = AudioResult()
        r2 = AudioResult()
        assert r1.task_id != r2.task_id
