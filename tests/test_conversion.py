"""Tests for ABC → MIDI conversion."""

import pytest

# Sample ABC notation for testing
SIMPLE_ABC = """X:1
T:Test Piece
M:4/4
L:1/8
Q:1/4=120
K:C
CDEF GABc | c2B2 A2G2 | F2E2 D2C2 | C8 |]
"""

MULTI_VOICE_ABC = """X:1
T:Two Voice Test
M:4/4
L:1/4
Q:1/4=100
K:C
V:1 name="Melody"
V:2 name="Bass"
[V:1]
C D E F | G A B c |
[V:2]
C, E, G, C | G,, B,, D, G, |
"""


class TestABCParsing:
    def test_parse_simple_abc(self):
        from hachimi.conversion.abc_to_midi import parse_abc

        score = parse_abc(SIMPLE_ABC)
        assert score is not None
        parts = list(score.parts)
        assert len(parts) >= 1

    def test_parse_multi_voice(self):
        from hachimi.conversion.abc_to_midi import parse_abc

        score = parse_abc(MULTI_VOICE_ABC)
        assert score is not None
        parts = list(score.parts)
        assert len(parts) >= 2

    def test_invalid_abc_raises(self):
        from hachimi.conversion.abc_to_midi import parse_abc

        with pytest.raises(ValueError):
            parse_abc("this is not valid abc notation at all")


class TestABCToMIDI:
    def test_convert_to_midi(self, tmp_path):
        from hachimi.conversion.abc_to_midi import abc_to_midi
        from hachimi.core.schemas import InstrumentAssignment, ScoreResult

        score_result = ScoreResult(
            abc_notation=SIMPLE_ABC,
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

        midi_path = tmp_path / "test.mid"
        result = abc_to_midi(score_result, output_path=midi_path)
        assert result.exists()
        assert result.stat().st_size > 0

    def test_midi_duration(self, tmp_path):
        from hachimi.conversion.abc_to_midi import abc_to_midi, get_midi_duration
        from hachimi.core.schemas import ScoreResult

        score_result = ScoreResult(
            abc_notation=SIMPLE_ABC,
            key="C",
            time_signature="4/4",
            tempo=120,
        )

        midi_path = tmp_path / "test_dur.mid"
        abc_to_midi(score_result, output_path=midi_path)
        duration = get_midi_duration(midi_path)
        assert duration > 0
