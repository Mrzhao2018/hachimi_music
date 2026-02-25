"""Tests for instrument mapper."""

from hachimi.conversion.instrument_mapper import (
    assign_midi_channels,
    get_instrument_name,
    lookup_instrument,
)


class TestLookupInstrument:
    def test_exact_match(self):
        assert lookup_instrument("piano") == 0
        assert lookup_instrument("violin") == 40
        assert lookup_instrument("flute") == 73
        assert lookup_instrument("trumpet") == 56

    def test_case_insensitive(self):
        assert lookup_instrument("Piano") == 0
        assert lookup_instrument("VIOLIN") == 40
        assert lookup_instrument("Acoustic Grand Piano") == 0

    def test_chinese_names(self):
        assert lookup_instrument("钢琴") == 0
        assert lookup_instrument("小提琴") == 40
        assert lookup_instrument("大提琴") == 42
        assert lookup_instrument("长笛") == 73

    def test_fuzzy_match(self):
        assert lookup_instrument("electric piano") == 4
        assert lookup_instrument("nylon guitar") == 24

    def test_percussion(self):
        assert lookup_instrument("drums") == -1
        assert lookup_instrument("drum kit") == -1
        assert lookup_instrument("鼓") == -1

    def test_unknown_defaults_to_piano(self):
        assert lookup_instrument("theremin_xyz_unknown") == 0


class TestAssignMidiChannels:
    def test_single_instrument(self):
        result = assign_midi_channels([{"instrument": "piano", "gm_program": 0}])
        assert len(result) == 1
        assert result[0]["midi_channel"] == 0

    def test_multiple_instruments(self):
        instruments = [
            {"instrument": "piano", "gm_program": 0},
            {"instrument": "violin", "gm_program": 40},
            {"instrument": "flute", "gm_program": 73},
        ]
        result = assign_midi_channels(instruments)
        channels = [r["midi_channel"] for r in result]
        assert len(set(channels)) == 3  # All unique
        assert 9 not in channels  # Channel 9 reserved for drums

    def test_percussion_gets_channel_9(self):
        instruments = [
            {"instrument": "piano", "gm_program": 0},
            {"instrument": "drums", "gm_program": -1},
        ]
        result = assign_midi_channels(instruments)
        assert result[1]["midi_channel"] == 9

    def test_auto_lookup_program(self):
        result = assign_midi_channels([{"instrument": "cello"}])
        assert result[0]["gm_program"] == 42


class TestGetInstrumentName:
    def test_known_program(self):
        name = get_instrument_name(0)
        assert "piano" in name.lower()

    def test_violin(self):
        name = get_instrument_name(40)
        assert "violin" in name.lower()
