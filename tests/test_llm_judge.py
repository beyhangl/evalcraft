"""Tests for evalcraft.eval.llm_judge — LLM-as-Judge scorers."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from evalcraft.core.models import AgentRun, Cassette, Span, SpanKind
from evalcraft.eval.llm_judge import (
    _call_judge,
    assert_custom_criteria,
    assert_factual_consistency,
    assert_output_semantic,
    assert_tone,
)
from evalcraft.eval._utils import get_cassette as _get_cassette


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def weather_cassette():
    c = Cassette(name="weather_test", agent_name="weather_agent")
    c.output_text = "It's 18°C and cloudy in Paris right now."
    c.add_span(Span(kind=SpanKind.AGENT_OUTPUT, output=c.output_text))
    return c


@pytest.fixture
def empty_output_cassette():
    c = Cassette(name="empty_test")
    c.output_text = ""
    return c


def _mock_openai_response(content: str):
    """Create a mock OpenAI response object."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ──────────────────────────────────────────────
# _call_judge
# ──────────────────────────────────────────────

class TestCallJudge:
    def test_openai_provider_parses_json(self):
        judge_response = json.dumps({"pass": True, "reason": "Looks good", "score": 0.95})
        mock_openai = MagicMock()
        client = MagicMock()
        client.chat.completions.create.return_value = _mock_openai_response(judge_response)
        mock_openai.OpenAI.return_value = client

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = _call_judge("test prompt", provider="openai", model="gpt-4o-mini")

        assert result["pass"] is True
        assert result["reason"] == "Looks good"
        assert result["score"] == 0.95

    def test_openai_handles_invalid_json(self):
        mock_openai = MagicMock()
        client = MagicMock()
        client.chat.completions.create.return_value = _mock_openai_response("not json")
        mock_openai.OpenAI.return_value = client

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = _call_judge("test prompt", provider="openai")

        assert result["pass"] is False
        assert "invalid JSON" in result["reason"]

    def test_normalises_alternate_keys(self):
        # Some models return "passed" instead of "pass"
        judge_response = json.dumps({"passed": True, "reason": "OK"})
        mock_openai = MagicMock()
        client = MagicMock()
        client.chat.completions.create.return_value = _mock_openai_response(judge_response)
        mock_openai.OpenAI.return_value = client

        with patch.dict("sys.modules", {"openai": mock_openai}):
            result = _call_judge("test prompt", provider="openai")

        assert result["pass"] is True

    def test_unsupported_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported judge provider"):
            _call_judge("test prompt", provider="unsupported")


# ──────────────────────────────────────────────
# assert_output_semantic
# ──────────────────────────────────────────────

class TestAssertOutputSemantic:
    @patch("evalcraft.eval.llm_judge._call_judge")
    def test_passes_when_criteria_met(self, mock_judge, weather_cassette):
        mock_judge.return_value = {"pass": True, "reason": "", "score": 1.0}

        result = assert_output_semantic(
            weather_cassette, criteria="Mentions temperature and city name"
        )

        assert result.passed
        assert result.name == "assert_output_semantic('Mentions temperature and city name')"

    @patch("evalcraft.eval.llm_judge._call_judge")
    def test_fails_when_criteria_not_met(self, mock_judge, weather_cassette):
        mock_judge.return_value = {
            "pass": False,
            "reason": "Output does not mention humidity",
            "score": 0.3,
        }

        result = assert_output_semantic(weather_cassette, criteria="Mentions humidity")

        assert not result.passed
        assert "humidity" in result.message

    def test_fails_on_empty_output(self, empty_output_cassette):
        result = assert_output_semantic(empty_output_cassette, criteria="Any criteria")
        assert not result.passed
        assert "no output" in result.message.lower()

    @patch("evalcraft.eval.llm_judge._call_judge")
    def test_works_with_agent_run(self, mock_judge, weather_cassette):
        mock_judge.return_value = {"pass": True, "reason": "", "score": 1.0}
        run = AgentRun(cassette=weather_cassette)

        result = assert_output_semantic(run, criteria="Has weather info")

        assert result.passed

    @patch("evalcraft.eval.llm_judge._call_judge")
    def test_passes_provider_and_model(self, mock_judge, weather_cassette):
        mock_judge.return_value = {"pass": True, "reason": "", "score": 1.0}

        assert_output_semantic(
            weather_cassette,
            criteria="test",
            provider="anthropic",
            model="claude-haiku-4-5-20251001",
        )

        mock_judge.assert_called_once()
        call_kwargs = mock_judge.call_args
        assert call_kwargs.kwargs["provider"] == "anthropic"
        assert call_kwargs.kwargs["model"] == "claude-haiku-4-5-20251001"


# ──────────────────────────────────────────────
# assert_factual_consistency
# ──────────────────────────────────────────────

class TestAssertFactualConsistency:
    @patch("evalcraft.eval.llm_judge._call_judge")
    def test_passes_when_consistent(self, mock_judge, weather_cassette):
        mock_judge.return_value = {"pass": True, "reason": "", "score": 1.0}

        result = assert_factual_consistency(
            weather_cassette, ground_truth="Paris is 18°C and cloudy"
        )

        assert result.passed
        assert result.name == "assert_factual_consistency"

    @patch("evalcraft.eval.llm_judge._call_judge")
    def test_fails_when_inconsistent(self, mock_judge, weather_cassette):
        mock_judge.return_value = {
            "pass": False,
            "reason": "Output says cloudy, ground truth says sunny",
            "score": 0.2,
        }

        result = assert_factual_consistency(
            weather_cassette, ground_truth="Paris is 18°C and sunny"
        )

        assert not result.passed
        assert "sunny" in result.message

    def test_fails_on_empty_output(self, empty_output_cassette):
        result = assert_factual_consistency(
            empty_output_cassette, ground_truth="anything"
        )
        assert not result.passed


# ──────────────────────────────────────────────
# assert_tone
# ──────────────────────────────────────────────

class TestAssertTone:
    @patch("evalcraft.eval.llm_judge._call_judge")
    def test_passes_when_tone_matches(self, mock_judge, weather_cassette):
        mock_judge.return_value = {"pass": True, "reason": "", "score": 0.9}

        result = assert_tone(weather_cassette, expected="informative and concise")

        assert result.passed
        assert result.name == "assert_tone('informative and concise')"

    @patch("evalcraft.eval.llm_judge._call_judge")
    def test_fails_when_tone_wrong(self, mock_judge, weather_cassette):
        mock_judge.return_value = {
            "pass": False,
            "reason": "Output is informative, not humorous",
            "score": 0.1,
        }

        result = assert_tone(weather_cassette, expected="humorous and playful")

        assert not result.passed

    def test_fails_on_empty_output(self, empty_output_cassette):
        result = assert_tone(empty_output_cassette, expected="professional")
        assert not result.passed


# ──────────────────────────────────────────────
# assert_custom_criteria
# ──────────────────────────────────────────────

class TestAssertCustomCriteria:
    @patch("evalcraft.eval.llm_judge._call_judge")
    def test_passes_when_all_criteria_met(self, mock_judge, weather_cassette):
        mock_judge.return_value = {"pass": True, "reason": "", "score": 1.0}

        result = assert_custom_criteria(
            weather_cassette,
            criteria=["Mentions a city", "Includes temperature", "Uses Celsius"],
        )

        assert result.passed
        assert result.name == "assert_custom_criteria"

    @patch("evalcraft.eval.llm_judge._call_judge")
    def test_fails_when_criteria_not_met(self, mock_judge, weather_cassette):
        mock_judge.return_value = {
            "pass": False,
            "reason": "Does not use Fahrenheit",
            "score": 0.66,
        }

        result = assert_custom_criteria(
            weather_cassette,
            criteria=["Mentions a city", "Uses Fahrenheit"],
        )

        assert not result.passed

    def test_fails_on_empty_output(self, empty_output_cassette):
        result = assert_custom_criteria(
            empty_output_cassette, criteria=["Any criteria"]
        )
        assert not result.passed

    @patch("evalcraft.eval.llm_judge._call_judge")
    def test_require_all_false(self, mock_judge, weather_cassette):
        mock_judge.return_value = {"pass": True, "reason": "At least one matches", "score": 0.5}

        result = assert_custom_criteria(
            weather_cassette,
            criteria=["Mentions Paris", "Mentions London"],
            require_all=False,
        )

        assert result.passed
        # Verify the prompt mentions "at least ONE"
        call_args = mock_judge.call_args
        assert "ONE" in call_args.args[0]
