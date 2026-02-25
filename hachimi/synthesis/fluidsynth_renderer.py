"""MIDI to audio rendering using FluidSynth (SoundFont synthesis)."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from hachimi.core.config import AppConfig, get_config

logger = logging.getLogger(__name__)


class FluidSynthRenderer:
    """Render MIDI files to audio using FluidSynth and SoundFont files."""

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or get_config()

    def _find_soundfont(self) -> Path:
        """Find the configured SoundFont file."""
        sf_path = self.config.get_soundfont_path()
        if sf_path.exists():
            return sf_path

        # Try common locations in the soundfonts directory
        sf_dir = self.config.resolve_path(self.config.paths.soundfonts_dir)
        if sf_dir.exists():
            for ext in ("*.sf2", "*.sf3"):
                files = list(sf_dir.glob(ext))
                if files:
                    logger.info("Using SoundFont: %s", files[0])
                    return files[0]

        raise FileNotFoundError(
            f"SoundFont file not found at {sf_path}. "
            f"Please download a SoundFont (.sf2) file and place it in the "
            f"'{sf_dir}' directory. Run: python scripts/download_soundfonts.py"
        )

    def render(
        self,
        midi_path: str | Path,
        output_path: Optional[str | Path] = None,
        soundfont: Optional[str | Path] = None,
    ) -> Path:
        """
        Render a MIDI file to WAV audio using FluidSynth.

        Args:
            midi_path: Path to the MIDI file.
            output_path: Path for the output WAV file. If None, auto-generated.
            soundfont: Optional override for the SoundFont file path.

        Returns:
            Path to the generated WAV file.
        """
        # Ensure local FluidSynth is on PATH before attempting any rendering
        try:
            from scripts.install_fluidsynth import ensure_fluidsynth_path
            ensure_fluidsynth_path()
        except Exception:
            pass

        midi_path = Path(midi_path)
        if not midi_path.exists():
            raise FileNotFoundError(f"MIDI file not found: {midi_path}")

        # Resolve SoundFont
        if soundfont:
            sf_path = Path(soundfont)
        else:
            sf_path = self._find_soundfont()

        # Determine output path
        if output_path is None:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            output_path = Path(tmp.name)
            tmp.close()
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        sample_rate = self.config.synthesis.sample_rate

        # Try using midi2audio (Python wrapper around FluidSynth)
        try:
            return self._render_with_midi2audio(midi_path, output_path, sf_path, sample_rate)
        except Exception as e:
            logger.warning("midi2audio failed: %s. Trying fluidsynth CLI...", e)

        # Fallback: try FluidSynth CLI directly
        try:
            return self._render_with_cli(midi_path, output_path, sf_path, sample_rate)
        except Exception as e:
            logger.warning("FluidSynth CLI failed: %s. Trying pyfluidsynth...", e)

        # Fallback: try pyfluidsynth
        try:
            return self._render_with_pyfluidsynth(midi_path, output_path, sf_path, sample_rate)
        except Exception as e:
            logger.warning("pyfluidsynth failed: %s. Using built-in synthesizer...", e)

        # Ultimate fallback: pure-Python sine/saw wave synthesis (no FluidSynth needed)
        return self._render_with_pretty_midi(midi_path, output_path, sample_rate)

    def _render_with_midi2audio(
        self, midi_path: Path, output_path: Path, sf_path: Path, sample_rate: int
    ) -> Path:
        """Render using midi2audio library."""
        from midi2audio import FluidSynth

        logger.info("Rendering with midi2audio...")
        fs = FluidSynth(str(sf_path), sample_rate=sample_rate)
        fs.midi_to_audio(str(midi_path), str(output_path))
        logger.info("Audio rendered to: %s", output_path)
        return output_path

    def _render_with_cli(
        self, midi_path: Path, output_path: Path, sf_path: Path, sample_rate: int
    ) -> Path:
        """Render using fluidsynth command-line tool."""
        logger.info("Rendering with FluidSynth CLI...")
        cmd = [
            "fluidsynth",
            "-ni",
            str(sf_path),
            str(midi_path),
            "-F", str(output_path),
            "-r", str(sample_rate),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"FluidSynth CLI error: {result.stderr}")
        logger.info("Audio rendered to: %s", output_path)
        return output_path

    def _render_with_pyfluidsynth(
        self, midi_path: Path, output_path: Path, sf_path: Path, sample_rate: int
    ) -> Path:
        """Render using pyfluidsynth library directly."""
        import fluidsynth
        import numpy as np
        import scipy.io.wavfile as wav

        logger.info("Rendering with pyfluidsynth...")

        # Read MIDI events using mido
        import mido

        mid = mido.MidiFile(str(midi_path))
        fs = fluidsynth.Synth(samplerate=float(sample_rate))
        sfid = fs.sfload(str(sf_path))

        # Initialize all channels with default program
        for ch in range(16):
            fs.program_select(ch, sfid, 0, 0)

        # Calculate total time and pre-allocate buffer
        total_time = mid.length
        total_samples = int((total_time + 2.0) * sample_rate)  # +2s padding
        audio_buffer = np.zeros(total_samples * 2, dtype=np.float32)  # stereo

        sample_pos = 0
        for msg in mid:
            if msg.time > 0:
                n_samples = int(msg.time * sample_rate)
                if n_samples > 0 and sample_pos + n_samples * 2 <= len(audio_buffer):
                    samples = fs.get_samples(n_samples)
                    end_pos = sample_pos + len(samples)
                    if end_pos <= len(audio_buffer):
                        audio_buffer[sample_pos:end_pos] = samples
                    sample_pos = end_pos

            if msg.type == "note_on":
                fs.noteon(msg.channel, msg.note, msg.velocity)
            elif msg.type == "note_off":
                fs.noteoff(msg.channel, msg.note)
            elif msg.type == "program_change":
                fs.program_select(msg.channel, sfid, 0, msg.program)
            elif msg.type == "control_change":
                fs.cc(msg.channel, msg.control, msg.value)

        # Get remaining samples (release tails)
        remaining = int(1.5 * sample_rate)
        tail_samples = fs.get_samples(remaining)
        end_pos = min(sample_pos + len(tail_samples), len(audio_buffer))
        audio_buffer[sample_pos:end_pos] = tail_samples[: end_pos - sample_pos]

        fs.delete()

        # Convert to 16-bit WAV
        audio_buffer = audio_buffer[: end_pos]
        audio_stereo = audio_buffer.reshape(-1, 2)

        # Normalize
        max_val = np.max(np.abs(audio_stereo))
        if max_val > 0:
            audio_stereo = audio_stereo / max_val * 0.95

        audio_int16 = (audio_stereo * 32767).astype(np.int16)
        wav.write(str(output_path), sample_rate, audio_int16)

        logger.info("Audio rendered to: %s", output_path)
        return output_path

    def _render_with_pretty_midi(
        self, midi_path: Path, output_path: Path, sample_rate: int
    ) -> Path:
        """
        Fallback renderer using pretty_midi's built-in synthesizer.
        Produces basic waveforms without needing FluidSynth installed.
        Quality is lower but it always works.
        """
        import numpy as np
        import pretty_midi
        import scipy.io.wavfile as wav

        logger.info("Rendering with pretty_midi built-in synthesizer (no FluidSynth)...")
        logger.warning(
            "Using basic waveform synthesis. For better quality, install FluidSynth: "
            "https://github.com/FluidSynth/fluidsynth/releases"
        )

        pm = pretty_midi.PrettyMIDI(str(midi_path))
        # pretty_midi.synthesize() uses simple oscillator, no FluidSynth needed
        audio = pm.synthesize(fs=sample_rate)

        # Convert to stereo
        if audio.ndim == 1:
            audio = np.column_stack([audio, audio])

        # Normalize
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = audio / max_val * 0.95

        audio_int16 = (audio * 32767).astype(np.int16)
        wav.write(str(output_path), sample_rate, audio_int16)

        logger.info("Audio rendered to (basic synth): %s", output_path)
        return output_path
