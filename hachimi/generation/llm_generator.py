"""AI music score generation using LLM APIs."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from hachimi.core.config import AppConfig, get_config
from hachimi.core.schemas import InstrumentAssignment, MusicRequest, ScoreResult

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    path = _PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown fences, extra text, and raw ABC."""
    # Try direct JSON parse first
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Try extracting from markdown code fences
    patterns = [
        r"```json\s*\n(.*?)\n\s*```",
        r"```\s*\n(.*?)\n\s*```",
        r"\{[\s\S]*\}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(1) if match.lastindex else match.group(0)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    # Fallback: LLM returned raw ABC notation instead of JSON.
    # Try to salvage it by wrapping it into the expected structure.
    if _looks_like_abc(text):
        logger.warning("LLM returned raw ABC instead of JSON — wrapping automatically")
        return _wrap_raw_abc(text)

    raise ValueError(f"Could not extract valid JSON from LLM response:\n{text[:500]}")


def _looks_like_abc(text: str) -> bool:
    """Heuristic check: does this text look like ABC notation?"""
    lines = text.strip().split("\n")
    abc_headers = ("X:", "T:", "M:", "L:", "Q:", "K:", "V:")
    header_count = sum(1 for line in lines if any(line.strip().startswith(h) for h in abc_headers))
    has_notes = bool(re.search(r'[A-Ga-g][,\']*[0-9/]*', text))
    return header_count >= 2 or (header_count >= 1 and has_notes)


def _wrap_raw_abc(text: str) -> dict:
    """Wrap raw ABC notation text into the expected JSON structure."""
    lines = text.strip().split("\n")
    title = "Untitled"
    key = "C"
    time_sig = "4/4"
    tempo = 120
    instruments = []

    for line in lines:
        line_s = line.strip()
        if line_s.startswith("T:"):
            title = line_s[2:].strip()
        elif line_s.startswith("K:"):
            key = line_s[2:].strip().split()[0]  # e.g. "Cmaj" -> "Cmaj"
        elif line_s.startswith("M:"):
            time_sig = line_s[2:].strip()
        elif line_s.startswith("Q:"):
            # Q:1/4=120 or Q:120
            q_match = re.search(r'(\d+)\s*$', line_s)
            if q_match:
                tempo = int(q_match.group(1))
        elif line_s.startswith("V:"):
            # V:1 name="Melody" clef=treble
            v_match = re.match(r'V:(\S+)', line_s)
            name_match = re.search(r'name="([^"]+)"', line_s)
            voice_id = v_match.group(1) if v_match else str(len(instruments) + 1)
            voice_name = name_match.group(1) if name_match else f"Voice {voice_id}"
            instruments.append({
                "voice_id": voice_id,
                "voice_name": voice_name,
                "instrument": "Acoustic Grand Piano",
                "gm_program": 0,
            })

    if not instruments:
        instruments.append({
            "voice_id": "1",
            "voice_name": "melody",
            "instrument": "Acoustic Grand Piano",
            "gm_program": 0,
        })

    return {
        "title": title,
        "description": f"Auto-wrapped from raw ABC notation",
        "key": key,
        "time_signature": time_sig,
        "tempo": tempo,
        "instruments": instruments,
        "abc_notation": text.strip(),
    }


class LLMGenerator:
    """Generates music scores using OpenAI-compatible APIs."""

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or get_config()
        self._client = None

    def _get_client(self):
        import openai
        if self._client is None:
            api_key = self.config.get_ai_api_key()
            if not api_key:
                raise ValueError(
                    "API key not set. Set OPENAI_API_KEY env var "
                    "or configure it in settings."
                )
            self._client = openai.OpenAI(
                api_key=api_key,
                base_url=self.config.ai.base_url,
            )
        return self._client

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the OpenAI-compatible API and return the text response."""
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.config.ai.model,
            temperature=self.config.ai.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content

        # Check for truncation via finish_reason
        finish_reason = getattr(response.choices[0], 'finish_reason', None)
        if finish_reason == 'length':
            logger.warning("LLM output was truncated (finish_reason=length)")

        return content

    def _call_llm_with_audio(
        self, system_prompt: str, user_text: str, audio_path: str
    ) -> str:
        """Call an OpenAI-compatible multimodal API with audio input.

        Sends the audio file as a base64-encoded ``input_audio`` part,
        matching the Gemini OpenAI-compat endpoint format:
        https://ai.google.dev/gemini-api/docs/openai#音频理解

        Supported formats: wav, mp3, aiff, aac, ogg, flac.
        Inline audio limit: 20 MB.
        """
        import base64

        audio_p = Path(audio_path)
        if not audio_p.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        file_size_mb = audio_p.stat().st_size / (1024 * 1024)
        if file_size_mb > 20:
            raise ValueError(
                f"Audio file too large for inline upload ({file_size_mb:.1f} MB > 20 MB). "
                f"Consider converting to a lower bitrate."
            )

        ext = audio_p.suffix.lstrip(".").lower()
        # Normalise common extension variants
        format_map = {"mp3": "mp3", "wav": "wav", "wave": "wav",
                      "aiff": "aiff", "aac": "aac", "ogg": "ogg", "flac": "flac"}
        audio_format = format_map.get(ext, ext)

        audio_b64 = base64.b64encode(audio_p.read_bytes()).decode("ascii")
        logger.info(
            "Sending audio to multimodal LLM: %s (%.1f MB, format=%s)",
            audio_p.name, file_size_mb, audio_format,
        )

        client = self._get_client()
        response = client.chat.completions.create(
            model=self.config.ai.model,
            temperature=0.5,  # lower for analytical tasks
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": audio_b64,
                                "format": audio_format,
                            },
                        },
                    ],
                },
            ],
        )
        content = response.choices[0].message.content
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        if finish_reason == "length":
            logger.warning("Multimodal LLM output was truncated")

        # Log usage to help user verify audio was consumed
        usage = getattr(response, "usage", None)
        if usage:
            logger.info(
                "Audio analysis token usage: prompt=%s, completion=%s, total=%s",
                getattr(usage, "prompt_tokens", "?"),
                getattr(usage, "completion_tokens", "?"),
                getattr(usage, "total_tokens", "?"),
            )
        return content

    def analyze_audio(self, score: "ScoreResult", audio_path: str) -> dict:
        """Listen to generated audio and return improvement suggestions.

        Returns a dict with:
        - ``overall_rating`` (int 1-10)
        - ``overall_comment`` (str)
        - ``suggestions`` (list of dicts with type/severity/location/description/auto_fix_prompt)
        - ``audio_analyzed`` (bool): True if audio was actually sent to AI
        - ``analysis_mode`` (str): "multimodal" or "score_only"
        """
        system_prompt = _load_prompt("audio_feedback.txt")

        instruments_str = ", ".join(
            f"V{i.voice_id} {i.voice_name}: {i.instrument}" for i in score.instruments
        )

        # Distinguish prompt text depending on whether audio is included
        audio_instruction = (
            "I have attached the audio file. Please LISTEN to the audio carefully "
            "and provide feedback based on what you HEAR, not just the notation."
        )
        score_only_instruction = (
            "No audio file is available. Please analyze the ABC notation below "
            "and provide feedback based on the score only."
        )

        base_text = (
            f"Title: {score.title}\n"
            f"Key: {score.key}  Time: {score.time_signature}  Tempo: {score.tempo} BPM\n"
            f"Instruments: {instruments_str}\n\n"
            f"ABC notation:\n```\n{score.abc_notation}\n```\n\n"
        )

        audio_analyzed = False
        analysis_mode = "score_only"

        try:
            user_text = base_text + audio_instruction
            response_text = self._call_llm_with_audio(
                system_prompt, user_text, audio_path
            )
            feedback = _extract_json(response_text)
            audio_analyzed = True
            analysis_mode = "multimodal"
            logger.info("Audio analysis completed via multimodal API")
        except Exception as e:
            logger.warning(
                "Multimodal audio analysis failed (%s), falling back to score-only analysis",
                e,
            )
            # Fallback: analyse ABC text only (works with any LLM)
            user_text = base_text + score_only_instruction
            response_text = self._call_llm(system_prompt, user_text)
            feedback = _extract_json(response_text)

        # Add metadata
        feedback["audio_analyzed"] = audio_analyzed
        feedback["analysis_mode"] = analysis_mode
        feedback.setdefault("overall_rating", 5)
        feedback.setdefault("overall_comment", "")
        feedback.setdefault("suggestions", [])
        return feedback

    def suggest_params(self, prompt: str) -> dict:
        """Suggest musical parameters based on a natural-language description."""
        system_prompt = _load_prompt("suggest_params.txt")
        user_prompt = f"Description: {prompt}"

        response_text = self._call_llm(system_prompt, user_prompt)
        params = _extract_json(response_text)

        # Validate / clamp values
        valid_styles = {
            "classical", "pop", "jazz", "rock", "electronic",
            "folk", "blues", "latin", "ambient", "cinematic",
        }
        if params.get("style") not in valid_styles:
            params["style"] = "classical"

        tempo = params.get("tempo", 120)
        params["tempo"] = max(30, min(300, int(tempo)))

        measures = params.get("measures", 16)
        params["measures"] = max(4, min(64, int(measures)))

        if not params.get("instruments"):
            params["instruments"] = ["piano"]

        return params

    def compose(self, request: MusicRequest) -> ScoreResult:
        """
        Generate a music score from a natural language request.

        Uses a two-step approach for stability:
        1. Generate metadata (title, instruments, etc.) as small JSON
        2. Generate ABC notation as plain text
        3. Assemble into ScoreResult
        """
        meta_system = _load_prompt("compose_meta.txt")
        abc_template = _load_prompt("compose_abc.txt")

        instruments_str = ", ".join(request.instruments)
        meta_user = (
            f"Compose a piece: {request.prompt}\n"
            f"Style: {request.style.value}, Key: {request.key}, "
            f"Time: {request.time_signature}, Tempo: {request.tempo} BPM, "
            f"Instruments: {instruments_str}"
        )

        last_error = None

        for attempt in range(self.config.ai.max_retries + 1):
            try:
                # ── Step 1: Generate metadata ─────────────────────
                logger.info("Step 1: Generating metadata (attempt %d)...", attempt + 1)
                meta_text = self._call_llm(meta_system, meta_user)
                meta = _extract_json(meta_text)

                # Build instrument list
                instruments = []
                for inst_data in meta.get("instruments", []):
                    instruments.append(InstrumentAssignment(
                        voice_id=str(inst_data.get("voice_id", "1")),
                        voice_name=inst_data.get("voice_name", "melody"),
                        instrument=inst_data.get("instrument", "Acoustic Grand Piano"),
                        gm_program=inst_data.get("gm_program"),
                    ))

                if not instruments:
                    instruments.append(InstrumentAssignment(
                        voice_id="1", voice_name="melody",
                        instrument="Acoustic Grand Piano", gm_program=0,
                    ))

                # ── Step 2: Generate ABC notation ─────────────────
                voices_info = "\n".join(
                    f"- V:{i.voice_id} name=\"{i.voice_name}\" → {i.instrument} (GM {i.gm_program})"
                    for i in instruments
                )

                abc_prompt = abc_template.format(
                    title=meta.get("title", "Untitled"),
                    key=meta.get("key", request.key),
                    time_signature=meta.get("time_signature", request.time_signature),
                    tempo=meta.get("tempo", request.tempo),
                    measures=request.measures,
                    style=request.style.value,
                    voices_info=voices_info,
                    prompt=request.prompt,
                )

                logger.info("Step 2: Generating ABC notation...")
                abc_text = self._call_llm(
                    "You are a music notation expert. Output ONLY valid ABC notation, nothing else.",
                    abc_prompt,
                )

                # Clean up: strip markdown fences if any
                abc_clean = abc_text.strip()
                if abc_clean.startswith("```"):
                    abc_clean = re.sub(r'^```\w*\n?', '', abc_clean)
                    abc_clean = re.sub(r'\n?```\s*$', '', abc_clean)
                    abc_clean = abc_clean.strip()

                # ── Step 3: Assemble result ───────────────────────
                result = ScoreResult(
                    abc_notation=abc_clean,
                    title=meta.get("title", "Untitled"),
                    composer="Hachimi AI",
                    key=meta.get("key", request.key),
                    time_signature=meta.get("time_signature", request.time_signature),
                    tempo=meta.get("tempo", request.tempo),
                    instruments=instruments,
                    style=request.style.value,
                    description=meta.get("description", ""),
                )

                self._quick_validate_abc(
                    result.abc_notation,
                    expected_voices=len(instruments),
                )
                logger.info("Successfully generated score: %s", result.title)
                return result

            except Exception as e:
                last_error = e
                logger.warning("Attempt %d failed: %s", attempt + 1, e)
                if attempt == self.config.ai.max_retries:
                    raise RuntimeError(
                        f"Failed to generate valid music after "
                        f"{self.config.ai.max_retries + 1} attempts. "
                        f"Last error: {e}"
                    ) from e

        raise RuntimeError("Unexpected error in compose loop")

    @staticmethod
    def _quick_validate_abc(abc: str, expected_voices: int = 0) -> None:
        """Validate ABC notation structure, voice count, and truncation."""
        if not abc or not abc.strip():
            raise ValueError("ABC notation is empty")

        lines = abc.strip().split("\n")
        has_x = any(line.strip().startswith("X:") for line in lines)
        has_k = any(line.strip().startswith("K:") for line in lines)

        if not has_x:
            raise ValueError("ABC notation missing X: (reference number) field")
        if not has_k:
            raise ValueError("ABC notation missing K: (key) field")

        # Check for truncation: last non-empty line should end with | or |]
        non_empty = [l for l in lines if l.strip()]
        if non_empty:
            last_line = non_empty[-1].rstrip()
            # Header lines (X:, T:, etc.) don't need bar lines
            is_header = any(last_line.startswith(h) for h in ("X:", "T:", "M:", "L:", "Q:", "K:", "V:", "W:", "%%"))
            if not is_header and not last_line.endswith("|") and not last_line.endswith("|]"):
                raise ValueError(
                    f"ABC notation appears truncated — last line does not end with bar line: "
                    f"'{last_line[-60:]}'"
                )

        # Check voice count if expected
        if expected_voices > 1:
            # Count unique V: declarations ("V:1", "V:2", etc.)
            voice_ids = set()
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("V:"):
                    # Extract voice id (first token after V:)
                    vid = stripped[2:].split()[0] if len(stripped) > 2 else ""
                    voice_ids.add(vid)
            if len(voice_ids) < expected_voices:
                raise ValueError(
                    f"Expected {expected_voices} voices but found {len(voice_ids)}: "
                    f"{voice_ids}. The output may have been truncated."
                )

    def refine(self, score: "ScoreResult", modification_prompt: str) -> "ScoreResult":
        """Modify an existing score based on user instructions."""
        from hachimi.core.schemas import ScoreResult as SR

        refine_template = _load_prompt("refine.txt")
        instruments_str = ", ".join(
            f"{i.voice_name}: {i.instrument}" for i in score.instruments
        )

        prompt = refine_template.format(
            title=score.title,
            key=score.key,
            time_signature=score.time_signature,
            tempo=score.tempo,
            instruments=instruments_str,
            abc_notation=score.abc_notation,
            modification_prompt=modification_prompt,
        )

        system_prompt = _load_prompt("compose_system.txt")

        for attempt in range(self.config.ai.max_retries + 1):
            try:
                logger.info("Refining score (attempt %d)...", attempt + 1)
                response_text = self._call_llm(system_prompt, prompt)
                data = _extract_json(response_text)

                from hachimi.core.schemas import InstrumentAssignment
                instruments = []
                for inst_data in data.get("instruments", []):
                    instruments.append(InstrumentAssignment(
                        voice_id=str(inst_data.get("voice_id", "1")),
                        voice_name=inst_data.get("voice_name", "melody"),
                        instrument=inst_data.get("instrument", "Acoustic Grand Piano"),
                        gm_program=inst_data.get("gm_program"),
                    ))

                result = SR(
                    abc_notation=data["abc_notation"],
                    title=data.get("title", score.title),
                    composer="Hachimi AI",
                    key=data.get("key", score.key),
                    time_signature=data.get("time_signature", score.time_signature),
                    tempo=data.get("tempo", score.tempo),
                    instruments=instruments if instruments else score.instruments,
                    style=score.style,
                    description=data.get("description", ""),
                )
                final_instruments = instruments if instruments else score.instruments
                self._quick_validate_abc(
                    result.abc_notation,
                    expected_voices=len(final_instruments),
                )
                logger.info("Successfully refined score: %s", result.title)
                return result

            except Exception as e:
                logger.warning("Refine attempt %d failed: %s", attempt + 1, e)
                if attempt == self.config.ai.max_retries:
                    raise RuntimeError(f"Failed to refine after {self.config.ai.max_retries + 1} attempts: {e}") from e

        raise RuntimeError("Unexpected error in refine loop")
