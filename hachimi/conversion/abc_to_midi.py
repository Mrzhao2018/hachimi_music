"""Convert ABC notation to MIDI using music21."""

from __future__ import annotations

import copy
import logging
import tempfile
from pathlib import Path
from typing import Optional

from hachimi.conversion.instrument_mapper import assign_midi_channels, lookup_instrument
from hachimi.core.schemas import InstrumentAssignment, ScoreResult

logger = logging.getLogger(__name__)


def parse_abc(abc_notation: str):
    """
    Parse ABC notation string into a music21 Score object.

    Returns:
        music21.stream.Score object.

    Raises:
        ValueError: If the ABC notation cannot be parsed.
    """
    import music21

    try:
        score = music21.converter.parse(abc_notation, format="abc")
        return score
    except Exception as e:
        raise ValueError(f"Failed to parse ABC notation: {e}") from e


def apply_instruments_to_score(
    score,
    instruments: list[InstrumentAssignment],
) -> None:
    """
    Apply instrument assignments to a music21 Score.
    Sets the MIDI program for each part based on the instrument mapping.
    """
    import music21

    parts = list(score.parts)

    # Build instrument assignments with MIDI channels
    inst_dicts = []
    for inst in instruments:
        gm_program = inst.gm_program
        if gm_program is None:
            gm_program = lookup_instrument(inst.instrument)
        inst_dicts.append({
            "voice_id": inst.voice_id,
            "instrument": inst.instrument,
            "gm_program": gm_program,
        })

    inst_dicts = assign_midi_channels(inst_dicts)

    for i, part in enumerate(parts):
        if i < len(inst_dicts):
            inst_info = inst_dicts[i]
            gm_program = inst_info["gm_program"]
            midi_channel = inst_info["midi_channel"]

            # Create and assign instrument
            midi_instrument = music21.instrument.Instrument()
            midi_instrument.midiProgram = gm_program
            midi_instrument.midiChannel = midi_channel

            # Try to set a proper instrument name
            try:
                named_inst = music21.instrument.instrumentFromMidiProgram(gm_program)
                if named_inst:
                    part.insert(0, named_inst)
                    named_inst.midiChannel = midi_channel
                else:
                    part.insert(0, midi_instrument)
            except Exception:
                part.insert(0, midi_instrument)

            logger.info(
                "Part %d: %s → GM program %d, channel %d",
                i, inst_info["instrument"], gm_program, midi_channel,
            )
        else:
            logger.warning("No instrument assignment for part %d", i)


def abc_to_midi(
    score_result: ScoreResult,
    output_path: Optional[str | Path] = None,
) -> Path:
    """
    Convert a ScoreResult (containing ABC notation) to a MIDI file.

    Args:
        score_result: The AI-generated score result.
        output_path: Optional path to save the MIDI file. If None, uses a temp file.

    Returns:
        Path to the generated MIDI file.
    """
    logger.info("Converting ABC notation to MIDI...")

    # Parse ABC
    score = parse_abc(score_result.abc_notation)

    # Apply instruments
    if score_result.instruments:
        apply_instruments_to_score(score, score_result.instruments)

    # Set tempo if not already set
    import music21
    tempos = list(score.flat.getElementsByClass(music21.tempo.MetronomeMark))
    if not tempos:
        mm = music21.tempo.MetronomeMark(number=score_result.tempo)
        score.flat.insert(0, mm)

    # Determine output path
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".mid", delete=False)
        output_path = Path(tmp.name)
        tmp.close()
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure all parts have proper Measure objects.
    # music21's MIDI translator tries to expand repeats, which fails if
    # the stream contains repeat barlines but no Measure containers.
    for part in score.parts:
        if not list(part.getElementsByClass(music21.stream.Measure)):
            logger.info("Part missing Measure objects — calling makeMeasures()")
            new_part = part.makeMeasures(inPlace=False)
            # Replace contents
            part_index = list(score.parts).index(part)
            score.replace(part, new_part)

    # Try to expand repeats; if it fails, strip repeat barlines and proceed
    try:
        score = score.expandRepeats()
    except Exception as e:
        logger.warning("Could not expand repeats (%s), stripping them", e)
        for el in list(score.recurse()):
            if isinstance(el, music21.bar.Barline) and hasattr(el, 'type') and 'repeat' in str(getattr(el, 'type', '')).lower():
                el.activeSite.remove(el)
            elif isinstance(el, music21.bar.Repeat):
                el.activeSite.remove(el)

    # Write MIDI
    # deepcopy to avoid "object already in Stream" errors when music21
    # builds the conductor track — shared TimeSignature / KeySignature
    # instances across parts cause StreamException.
    score = copy.deepcopy(score)
    midi_file = music21.midi.translate.music21ObjectToMidiFile(score)
    midi_file.open(str(output_path), "wb")
    midi_file.write()
    midi_file.close()

    logger.info("MIDI file saved to: %s", output_path)
    return output_path


def get_midi_duration(midi_path: str | Path) -> float:
    """Get the duration of a MIDI file in seconds."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(midi_path))
    return pm.get_end_time()
