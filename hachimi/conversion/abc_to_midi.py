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


def _normalize_abc_voices(abc: str) -> str:
    """
    Normalize ABC voice format for music21 compatibility.

    music21 correctly parses the BLOCK format:
        V:1 name="Piano" clef=treble
        (all V:1 notes)
        V:2 name="Cello" clef=bass
        (all V:2 notes)

    But it FAILS with inline [V:n] marker format:
        V:1 name="Piano"
        V:2 name="Cello"
        [V:1] notes...
        [V:2] notes...

    This function detects the inline [V:n] format and converts it to block format.
    If the ABC already uses block format, it is returned unchanged.
    """
    import re

    lines = abc.strip().split('\n')
    has_inline = any(re.match(r'^\[V:', line) for line in lines)
    if not has_inline:
        return abc

    logger.debug("Detected inline [V:n] format — converting to block format for music21")

    header_lines: list[str] = []
    v_decls: dict[str, str] = {}          # voice_id → full V: declaration line
    voice_contents: dict[str, list[str]] = {}
    voice_order: list[str] = []
    current_voice: str | None = None

    for line in lines:
        m = re.match(r'^\[V:([^\]]+)\]\s*(.*)', line.rstrip())
        if m:
            vid = m.group(1).strip()
            rest = m.group(2).strip()
            current_voice = vid
            if vid not in voice_contents:
                voice_contents[vid] = []
                voice_order.append(vid)
            if rest:
                voice_contents[vid].append(rest)
        elif current_voice is not None:
            # Continuation line for current voice (could be empty — skip)
            stripped = line.rstrip()
            if stripped:
                voice_contents[current_voice].append(stripped)
        else:
            # Header area (before any [V:n] tag)
            m2 = re.match(r'^V:([^\s\]]+)(.*)', line.rstrip())
            if m2:
                vid = m2.group(1).strip()
                v_decls[vid] = line.rstrip()
            else:
                header_lines.append(line.rstrip())

    # Rebuild: pure headers first, then each voice block
    result: list[str] = list(header_lines)
    for vid in voice_order:
        result.append(v_decls.get(vid, f'V:{vid}'))
        result.extend(voice_contents.get(vid, []))

    normalized = '\n'.join(result)
    logger.debug("Normalized ABC:\n%s", normalized[:400])
    return normalized


def parse_abc(abc_notation: str):
    """
    Parse ABC notation string into a music21 Score object.

    Returns:
        music21.stream.Score object.

    Raises:
        ValueError: If the ABC notation cannot be parsed.
    """
    import music21

    # Normalize [V:n] inline format → block format before parsing
    abc_notation = _normalize_abc_voices(abc_notation)

    try:
        score = music21.converter.parse(abc_notation, format="abc")
    except Exception as e:
        raise ValueError(f"Failed to parse ABC notation: {e}") from e

    # Fix part offsets: some ABC formats cause music21 to place voices sequentially.
    # Reset every Part to offset 0 so all voices play in parallel.
    for part in score.parts:
        if part.offset != 0:
            logger.warning(
                "Part '%s' has non-zero offset %.2f — resetting to 0 for parallel playback",
                getattr(part, 'id', '?'), part.offset,
            )
            part.offset = 0.0

    return score


def apply_instruments_to_score(
    score,
    instruments: list[InstrumentAssignment],
) -> None:
    """
    Apply instrument assignments to a music21 Score.
    Sets the MIDI program for each part based on the instrument mapping.
    Matches by voice_id first (robust), falls back to index order.
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

    # Build voice_id → inst_info map for robust lookup
    voice_map: dict[str, dict] = {str(d["voice_id"]): d for d in inst_dicts}
    # Also map by lowercase voice_name (for matching music21 part.partName)
    voice_name_map: dict[str, dict] = {}
    for orig, assigned in zip(instruments, inst_dicts):
        voice_name_map[orig.voice_name.lower()] = assigned

    logger.info("Applying instruments: %d parts found, %d assignments", len(parts), len(inst_dicts))

    for i, part in enumerate(parts):
        # Strategy 1: match by voice_id from part.id (e.g. "V:1" or "1")
        raw_id = str(getattr(part, "id", "")).strip()
        voice_id = raw_id.lstrip("Vv").lstrip(":").strip() if raw_id else ""
        inst_info = voice_map.get(voice_id) or voice_map.get(raw_id)

        # Strategy 2: match by part partName (the name= attribute in ABC V: line)
        if inst_info is None:
            part_name = str(getattr(part, "partName", "") or "").strip().lower()
            if part_name:
                inst_info = voice_name_map.get(part_name)

        # Strategy 3: index-based fallback
        if inst_info is None and i < len(inst_dicts):
            inst_info = inst_dicts[i]
            logger.debug("Part %d (id=%r): no voice_id/name match, using index fallback → %s",
                         i, raw_id, inst_info["instrument"])

        if inst_info is None:
            logger.warning("Part %d (id=%r): no instrument assignment — skipping", i, raw_id)
            continue

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
            "Part %d (id=%r, voice=%r): %s → GM program %d, channel %d",
            i, raw_id, voice_id, inst_info["instrument"], gm_program, midi_channel,
        )


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
