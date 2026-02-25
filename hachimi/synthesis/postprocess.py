"""Audio post-processing: reverb, EQ, normalization, format conversion."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from hachimi.core.config import AppConfig, get_config

logger = logging.getLogger(__name__)


class PostProcessor:
    """Apply audio post-processing effects and format conversion."""

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or get_config()

    def apply(
        self,
        wav_path: str | Path,
        output_path: Optional[str | Path] = None,
        output_format: str = "mp3",
    ) -> Path:
        """
        Apply post-processing effects to a WAV file and optionally convert format.

        Args:
            wav_path: Path to the input WAV file.
            output_path: Path for the output file. If None, auto-generated.
            output_format: Output format ('wav' or 'mp3').

        Returns:
            Path to the processed audio file.
        """
        wav_path = Path(wav_path)
        if not wav_path.exists():
            raise FileNotFoundError(f"WAV file not found: {wav_path}")

        pp_config = self.config.postprocess

        # Try pedalboard for effects processing
        try:
            processed_wav = self._apply_pedalboard_effects(wav_path, pp_config)
        except ImportError:
            logger.warning("pedalboard not available, skipping audio effects")
            processed_wav = wav_path
        except Exception as e:
            logger.warning("pedalboard processing failed: %s, skipping effects", e)
            processed_wav = wav_path

        # Convert format if needed
        if output_format == "mp3":
            return self._convert_to_mp3(processed_wav, output_path, pp_config)
        else:
            if output_path and Path(output_path) != processed_wav:
                import shutil
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(processed_wav, output_path)
                return output_path
            return processed_wav

    def _apply_pedalboard_effects(self, wav_path: Path, pp_config) -> Path:
        """Apply audio effects using Spotify's pedalboard library."""
        import numpy as np
        from pedalboard import Compressor, Gain, Reverb
        from pedalboard.io import AudioFile

        logger.info("Applying audio effects with pedalboard...")

        # Read audio
        with AudioFile(str(wav_path)) as f:
            audio = f.read(f.frames)
            sample_rate = f.samplerate

        effects = []

        # Reverb
        if pp_config.reverb:
            effects.append(Reverb(
                room_size=pp_config.reverb_room_size,
                wet_level=0.2,
                dry_level=0.8,
            ))

        # Light compression for consistent volume
        effects.append(Compressor(
            threshold_db=-20,
            ratio=3.0,
            attack_ms=10,
            release_ms=100,
        ))

        # Normalize via gain
        if pp_config.normalize:
            max_val = np.max(np.abs(audio))
            if max_val > 0:
                target_db = -1.0  # Target peak level
                current_db = 20 * np.log10(max_val)
                gain_db = target_db - current_db
                effects.append(Gain(gain_db=gain_db))

        # Apply effects chain
        for effect in effects:
            audio = effect(audio, sample_rate)

        # Trim trailing silence (below -50 dB threshold)
        audio = self._trim_trailing_silence(audio, sample_rate, threshold_db=-50)

        # Write processed audio
        output = wav_path.with_stem(wav_path.stem + "_processed")
        with AudioFile(str(output), "w", sample_rate, audio.shape[0]) as f:
            f.write(audio)

        logger.info("Effects applied, saved to: %s", output)
        return output

    @staticmethod
    def _trim_trailing_silence(audio, sample_rate: int, threshold_db: float = -50):
        """Remove trailing silence from audio array.

        Args:
            audio: numpy array of shape (channels, samples)
            sample_rate: Sample rate in Hz
            threshold_db: Silence threshold in dB (default -50)

        Returns:
            Trimmed audio array
        """
        import numpy as np

        # Convert threshold to linear amplitude
        threshold = 10 ** (threshold_db / 20)

        # Compute amplitude envelope across all channels
        amplitude = np.max(np.abs(audio), axis=0)

        # Find the last sample above threshold
        above = np.where(amplitude > threshold)[0]
        if len(above) == 0:
            return audio  # All silence — keep as is

        last_sound = above[-1]

        # Keep 0.5 seconds of tail after last audible sample for natural decay
        tail_samples = int(0.5 * sample_rate)
        end = min(last_sound + tail_samples, audio.shape[1])

        trimmed = audio[:, :end]
        trimmed_sec = (audio.shape[1] - end) / sample_rate
        if trimmed_sec > 0.5:
            logger.info("Trimmed %.1f seconds of trailing silence", trimmed_sec)

        return trimmed

    def _convert_to_mp3(
        self, wav_path: Path, output_path: Optional[str | Path], pp_config
    ) -> Path:
        """Convert WAV to MP3 using pydub."""
        from pydub import AudioSegment

        logger.info("Converting to MP3...")

        audio = AudioSegment.from_wav(str(wav_path))

        # Apply fade in/out
        if pp_config.fade_in_ms > 0:
            audio = audio.fade_in(pp_config.fade_in_ms)
        if pp_config.fade_out_ms > 0:
            audio = audio.fade_out(pp_config.fade_out_ms)

        # Determine output path
        if output_path is None:
            output_path = wav_path.with_suffix(".mp3")
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        audio.export(str(output_path), format="mp3", bitrate="192k")
        logger.info("MP3 saved to: %s", output_path)
        return output_path
