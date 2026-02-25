"""Tests for configuration loading."""

from pathlib import Path

from hachimi.core.config import AppConfig, load_config


class TestConfig:
    def test_default_config(self):
        config = AppConfig()
        assert config.ai.base_url == "https://api.openai.com/v1"
        assert config.synthesis.sample_rate == 44100
        assert config.server.port == 8000

    def test_load_from_yaml(self):
        config = load_config()
        assert isinstance(config, AppConfig)
        assert config.ai.base_url.startswith("http")

    def test_resolve_path(self):
        config = AppConfig()
        p = config.resolve_path("output/test.wav")
        assert isinstance(p, Path)
        assert p.is_absolute()

    def test_get_output_dir(self):
        config = AppConfig()
        d = config.get_output_dir()
        assert d.exists()
        assert d.is_dir()
