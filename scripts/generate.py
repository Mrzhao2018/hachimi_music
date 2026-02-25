"""CLI entry point: generate music from the command line."""

from __future__ import annotations

import argparse
import logging
import sys

from hachimi.core.config import load_config
from hachimi.core.pipeline import MusicPipeline
from hachimi.core.schemas import MusicRequest, MusicStyle, OutputFormat


def main():
    parser = argparse.ArgumentParser(
        description="Hachimi Music - Generate music from natural language descriptions",
    )
    parser.add_argument(
        "prompt",
        type=str,
        help="Description of the music to generate",
    )
    parser.add_argument(
        "--style",
        type=str,
        default="classical",
        choices=[s.value for s in MusicStyle],
        help="Musical style (default: classical)",
    )
    parser.add_argument("--key", type=str, default="C", help="Musical key (default: C)")
    parser.add_argument("--time-signature", type=str, default="4/4", help="Time signature (default: 4/4)")
    parser.add_argument("--tempo", type=int, default=120, help="Tempo in BPM (default: 120)")
    parser.add_argument("--measures", type=int, default=16, help="Number of measures (default: 16)")
    parser.add_argument(
        "--instruments",
        type=str,
        nargs="+",
        default=["piano"],
        help="Instruments to use (default: piano)",
    )
    parser.add_argument(
        "--format",
        type=str,
        default="mp3",
        choices=["mp3", "wav"],
        help="Output audio format (default: mp3)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config YAML file",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Load config
    config = load_config(args.config)

    # Build request
    request = MusicRequest(
        prompt=args.prompt,
        style=MusicStyle(args.style),
        key=args.key,
        time_signature=args.time_signature,
        tempo=args.tempo,
        measures=args.measures,
        instruments=args.instruments,
        output_format=OutputFormat(args.format),
    )

    print(f"\n🎵 Hachimi Music Generator")
    print(f"  Prompt: {request.prompt}")
    print(f"  Style: {request.style.value} | Key: {request.key} | "
          f"Tempo: {request.tempo} BPM | Time: {request.time_signature}")
    print(f"  Instruments: {', '.join(request.instruments)}")
    print(f"  Measures: {request.measures} | Format: {request.output_format.value}")
    print()

    # Run pipeline
    pipeline = MusicPipeline(config)

    def progress_cb(status, message):
        print(f"  [{status.value}] {message}")

    result = pipeline.generate(request, progress_callback=progress_cb)

    if result.status.value == "failed":
        print(f"\n❌ Generation failed: {result.error_message}")
        sys.exit(1)

    print(f"\n✅ Music generated successfully!")
    if result.score:
        print(f"  Title: {result.score.title}")
        print(f"  Description: {result.score.description}")
    if result.duration_seconds:
        print(f"  Duration: {result.duration_seconds:.1f}s")
    print(f"  Audio: {result.audio_path}")
    if result.midi_path:
        print(f"  MIDI: {result.midi_path}")
    print()

    # Print ABC notation
    if result.abc_notation:
        print("── ABC Notation ──")
        print(result.abc_notation)
        print()


if __name__ == "__main__":
    main()
