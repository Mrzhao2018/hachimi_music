"""Application configuration loader."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class AIConfig(BaseModel):
    base_url: str = "https://api.openai.com/v1"  # OpenAI-compatible endpoint
    model: str = "gpt-4o"
    api_key: str = ""
    max_retries: int = 3
    temperature: float = 0.8


class MusicConfig(BaseModel):
    default_tempo: int = 120
    default_key: str = "C"
    default_time_signature: str = "4/4"
    default_style: str = "classical"
    max_measures: int = 64


class SynthesisConfig(BaseModel):
    soundfont: str = "soundfonts/FluidR3_GM.sf2"
    sample_rate: int = 44100
    output_format: str = "mp3"


class PostprocessConfig(BaseModel):
    reverb: bool = True
    reverb_room_size: float = 0.3
    normalize: bool = True
    fade_in_ms: int = 100
    fade_out_ms: int = 500


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )


class PathsConfig(BaseModel):
    output_dir: str = "output"
    soundfonts_dir: str = "soundfonts"


class AppConfig(BaseModel):
    ai: AIConfig = Field(default_factory=AIConfig)
    music: MusicConfig = Field(default_factory=MusicConfig)
    synthesis: SynthesisConfig = Field(default_factory=SynthesisConfig)
    postprocess: PostprocessConfig = Field(default_factory=PostprocessConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    @property
    def project_root(self) -> Path:
        return _PROJECT_ROOT

    def resolve_path(self, relative_path: str) -> Path:
        """Resolve a relative path against project root."""
        p = Path(relative_path)
        if p.is_absolute():
            return p
        return _PROJECT_ROOT / p

    def get_soundfont_path(self) -> Path:
        return self.resolve_path(self.synthesis.soundfont)

    def get_output_dir(self) -> Path:
        d = self.resolve_path(self.paths.output_dir)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def get_ai_api_key(self) -> str:
        """Get API key: config memory > .env file > environment variable."""
        if self.ai.api_key:
            return self.ai.api_key
        # Try .env file
        env_key = _load_env_key()
        if env_key:
            return env_key
        return os.environ.get("OPENAI_API_KEY", "")


def load_config(config_path: Optional[str | Path] = None) -> AppConfig:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = _PROJECT_ROOT / "config" / "settings.yaml"
    else:
        config_path = Path(config_path)

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return AppConfig(**data)
    else:
        return AppConfig()


def save_config(config: Optional["AppConfig"] = None, config_path: Optional[str | Path] = None) -> None:
    """Save current configuration to YAML file."""
    if config is None:
        config = get_config()
    if config_path is None:
        config_path = _PROJECT_ROOT / "config" / "settings.yaml"
    else:
        config_path = Path(config_path)

    config_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "ai": {
            "base_url": config.ai.base_url,
            "model": config.ai.model,
            "max_retries": config.ai.max_retries,
            "temperature": config.ai.temperature,
        },
        "music": {
            "default_tempo": config.music.default_tempo,
            "default_key": config.music.default_key,
            "default_time_signature": config.music.default_time_signature,
            "default_style": config.music.default_style,
            "max_measures": config.music.max_measures,
        },
        "synthesis": {
            "soundfont": config.synthesis.soundfont,
            "sample_rate": config.synthesis.sample_rate,
            "output_format": config.synthesis.output_format,
        },
        "postprocess": {
            "reverb": config.postprocess.reverb,
            "reverb_room_size": config.postprocess.reverb_room_size,
            "normalize": config.postprocess.normalize,
            "fade_in_ms": config.postprocess.fade_in_ms,
            "fade_out_ms": config.postprocess.fade_out_ms,
        },
        "server": {
            "host": config.server.host,
            "port": config.server.port,
            "cors_origins": config.server.cors_origins,
        },
        "paths": {
            "output_dir": config.paths.output_dir,
            "soundfonts_dir": config.paths.soundfonts_dir,
        },
    }

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Save API key separately to .env (gitignored)
    if config.ai.api_key:
        _save_env_key(config.ai.api_key)


def _load_env_key() -> str:
    """Load OPENAI_API_KEY from project .env file."""
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.exists():
        return ""
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key.strip() == "OPENAI_API_KEY":
                return value.strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _save_env_key(api_key: str) -> None:
    """Save OPENAI_API_KEY to project .env file (gitignored)."""
    env_path = _PROJECT_ROOT / ".env"
    lines: list[str] = []
    replaced = False

    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, _ = stripped.partition("=")
                if k.strip() == "OPENAI_API_KEY":
                    lines.append(f'OPENAI_API_KEY={api_key}')
                    replaced = True
                    continue
            lines.append(line)

    if not replaced:
        lines.append(f'OPENAI_API_KEY={api_key}')

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# Global config singleton
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the global configuration (lazy-loaded)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
