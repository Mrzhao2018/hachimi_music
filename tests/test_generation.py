"""Tests for the LLM generator module (JSON extraction)."""

from hachimi.generation.llm_generator import _extract_json


class TestExtractJSON:
    def test_plain_json(self):
        text = '{"title": "Test", "key": "C"}'
        result = _extract_json(text)
        assert result["title"] == "Test"

    def test_json_in_code_fence(self):
        text = '```json\n{"title": "Test", "tempo": 120}\n```'
        result = _extract_json(text)
        assert result["title"] == "Test"
        assert result["tempo"] == 120

    def test_json_with_surrounding_text(self):
        text = 'Here is the result:\n{"title": "Sunrise", "key": "G"}\nEnjoy!'
        result = _extract_json(text)
        assert result["title"] == "Sunrise"

    def test_invalid_json_raises(self):
        import pytest
        with pytest.raises(ValueError):
            _extract_json("This is not JSON at all")

    def test_json_with_whitespace(self):
        text = '\n\n  {"title": "Spaces"}\n\n'
        result = _extract_json(text)
        assert result["title"] == "Spaces"
