"""Instrument name to General MIDI program number mapping."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# General MIDI Program Number mapping
# Reference: https://www.midi.org/specifications-old/item/gm-level-1-sound-set
GM_INSTRUMENTS: dict[str, int] = {
    # Piano (0-7)
    "acoustic grand piano": 0,
    "grand piano": 0,
    "piano": 0,
    "bright acoustic piano": 1,
    "electric grand piano": 2,
    "honky-tonk piano": 3,
    "electric piano 1": 4,
    "electric piano": 4,
    "rhodes": 4,
    "electric piano 2": 5,
    "harpsichord": 6,
    "clavinet": 7,

    # Chromatic Percussion (8-15)
    "celesta": 8,
    "glockenspiel": 9,
    "music box": 10,
    "vibraphone": 11,
    "marimba": 12,
    "xylophone": 13,
    "tubular bells": 14,
    "dulcimer": 15,

    # Organ (16-23)
    "drawbar organ": 16,
    "organ": 16,
    "percussive organ": 17,
    "rock organ": 18,
    "church organ": 19,
    "reed organ": 20,
    "accordion": 21,
    "harmonica": 22,
    "tango accordion": 23,

    # Guitar (24-31)
    "acoustic guitar nylon": 24,
    "nylon guitar": 24,
    "classical guitar": 24,
    "acoustic guitar steel": 25,
    "acoustic guitar": 25,
    "steel guitar": 25,
    "electric guitar jazz": 26,
    "jazz guitar": 26,
    "electric guitar clean": 27,
    "clean guitar": 27,
    "electric guitar": 27,
    "electric guitar muted": 28,
    "overdriven guitar": 29,
    "distortion guitar": 30,
    "guitar harmonics": 31,

    # Bass (32-39)
    "acoustic bass": 32,
    "upright bass": 32,
    "double bass": 32,
    "contrabass": 32,
    "electric bass finger": 33,
    "electric bass": 33,
    "bass": 33,
    "electric bass pick": 34,
    "fretless bass": 35,
    "slap bass 1": 36,
    "slap bass": 36,
    "slap bass 2": 37,
    "synth bass 1": 38,
    "synth bass": 38,
    "synth bass 2": 39,

    # Strings (40-47)
    "violin": 40,
    "viola": 41,
    "cello": 42,
    "contrabass strings": 43,
    "tremolo strings": 44,
    "pizzicato strings": 45,
    "orchestral harp": 46,
    "harp": 46,
    "timpani": 47,

    # Ensemble (48-55)
    "string ensemble 1": 48,
    "string ensemble": 48,
    "strings": 48,
    "string ensemble 2": 49,
    "synth strings 1": 50,
    "synth strings": 50,
    "synth strings 2": 51,
    "choir aahs": 52,
    "choir": 52,
    "voice oohs": 53,
    "synth voice": 54,
    "orchestra hit": 55,

    # Brass (56-63)
    "trumpet": 56,
    "trombone": 57,
    "tuba": 58,
    "muted trumpet": 59,
    "french horn": 60,
    "horn": 60,
    "brass section": 61,
    "brass": 61,
    "synth brass 1": 62,
    "synth brass": 62,
    "synth brass 2": 63,

    # Reed (64-71)
    "soprano sax": 64,
    "alto sax": 65,
    "alto saxophone": 65,
    "saxophone": 65,
    "sax": 65,
    "tenor sax": 66,
    "tenor saxophone": 66,
    "baritone sax": 67,
    "oboe": 68,
    "english horn": 69,
    "bassoon": 70,
    "clarinet": 71,

    # Pipe (72-79)
    "piccolo": 72,
    "flute": 73,
    "recorder": 74,
    "pan flute": 75,
    "blown bottle": 76,
    "shakuhachi": 77,
    "whistle": 78,
    "ocarina": 79,

    # Synth Lead (80-87)
    "lead square": 80,
    "square wave": 80,
    "lead sawtooth": 81,
    "sawtooth": 81,
    "synth lead": 81,
    "lead calliope": 82,
    "lead chiff": 83,
    "lead charang": 84,
    "lead voice": 85,
    "lead fifths": 86,
    "lead bass+lead": 87,

    # Synth Pad (88-95)
    "pad new age": 88,
    "new age pad": 88,
    "pad warm": 89,
    "warm pad": 89,
    "synth pad": 89,
    "pad polysynth": 90,
    "pad choir": 91,
    "pad bowed": 92,
    "pad metallic": 93,
    "pad halo": 94,
    "pad sweep": 95,

    # Synth Effects (96-103)
    "fx rain": 96,
    "fx soundtrack": 97,
    "fx crystal": 98,
    "fx atmosphere": 99,
    "fx brightness": 100,
    "fx goblins": 101,
    "fx echoes": 102,
    "fx sci-fi": 103,

    # Ethnic (104-111)
    "sitar": 104,
    "banjo": 105,
    "shamisen": 106,
    "koto": 107,
    "kalimba": 108,
    "bag pipe": 109,
    "bagpipe": 109,
    "fiddle": 110,
    "shanai": 111,

    # Percussive (112-119)
    "tinkle bell": 112,
    "agogo": 113,
    "steel drums": 114,
    "woodblock": 115,
    "taiko drum": 116,
    "taiko": 116,
    "melodic tom": 117,
    "synth drum": 118,
    "reverse cymbal": 119,

    # Sound Effects (120-127)
    "guitar fret noise": 120,
    "breath noise": 121,
    "seashore": 122,
    "bird tweet": 123,
    "telephone ring": 124,
    "helicopter": 125,
    "applause": 126,
    "gunshot": 127,

    # Chinese instrument aliases (中文乐器别名)
    "钢琴": 0,
    "小提琴": 40,
    "中提琴": 41,
    "大提琴": 42,
    "低音提琴": 43,
    "竖琴": 46,
    "长笛": 73,
    "双簧管": 68,
    "单簧管": 71,
    "大管": 70,
    "小号": 56,
    "长号": 57,
    "大号": 58,
    "圆号": 60,
    "萨克斯": 65,
    "吉他": 25,
    "贝斯": 33,
    "鼓": -1,  # Special: drums go to channel 9
    "架子鼓": -1,
    "打击乐": -1,
    "drums": -1,
    "drum kit": -1,
    "drum set": -1,
    "percussion": -1,
}


def lookup_instrument(name: str) -> int:
    """
    Look up GM program number for an instrument name.

    Returns:
        GM program number (0-127), or -1 for percussion (channel 9).
    """
    normalized = name.strip().lower()

    # Direct match
    if normalized in GM_INSTRUMENTS:
        return GM_INSTRUMENTS[normalized]

    # Fuzzy match: check if any key is contained in the input or vice versa
    for key, program in GM_INSTRUMENTS.items():
        if key in normalized or normalized in key:
            logger.debug("Fuzzy matched '%s' → '%s' (program %d)", name, key, program)
            return program

    logger.warning("Unknown instrument '%s', defaulting to Acoustic Grand Piano (0)", name)
    return 0


def get_instrument_name(program: int) -> str:
    """Get the standard instrument name for a GM program number."""
    # Reverse lookup - find first match
    for name, prog in GM_INSTRUMENTS.items():
        if prog == program and not any(ord(c) > 127 for c in name):
            return name.title()
    return f"Program {program}"


def assign_midi_channels(
    instruments: list[dict[str, any]],
) -> list[dict[str, any]]:
    """
    Assign MIDI channels to a list of instrument specifications.
    Channel 9 is reserved for percussion.
    Channels 0-8 and 10-15 are available for melodic instruments.

    Args:
        instruments: List of dicts with at least 'instrument' and 'gm_program' keys.

    Returns:
        Same list with 'midi_channel' added to each dict.
    """
    melodic_channels = [i for i in range(16) if i != 9]
    channel_idx = 0

    result = []
    for inst in instruments:
        inst = dict(inst)  # Copy
        gm_program = inst.get("gm_program")

        if gm_program is None:
            gm_program = lookup_instrument(inst.get("instrument", "piano"))
            inst["gm_program"] = gm_program

        if gm_program == -1:
            # Percussion
            inst["midi_channel"] = 9
            inst["gm_program"] = 0  # Standard drum kit
        else:
            if channel_idx < len(melodic_channels):
                inst["midi_channel"] = melodic_channels[channel_idx]
                channel_idx += 1
            else:
                logger.warning("No more MIDI channels available, reusing channel 0")
                inst["midi_channel"] = 0

        result.append(inst)

    return result
