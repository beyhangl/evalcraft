"""Tests for the opt-in judge-call cache (issue #21).

The network boundary (``_provider_call``) is stubbed with a counter, so these
tests never make a real model call and can assert exactly when the model would
have been hit vs served from cache.
"""

import pytest

import evalcraft.eval._utils as utils
from evalcraft.eval._utils import call_llm_judge
from evalcraft.eval.judge_cache import (
    ENV_CACHE_PATH,
    JudgeCache,
    JudgeCacheMiss,
    use_judge_cache,
)

JUDGE_JSON = '{"pass": true, "reason": "ok", "score": 1.0}'


@pytest.fixture
def counting_provider(monkeypatch):
    """Replace the network boundary with a counter; returns the call counter."""
    calls = {"n": 0}

    def fake_provider_call(prompt, *, system_prompt, provider, model, api_key, temperature):
        calls["n"] += 1
        return JUDGE_JSON

    monkeypatch.setattr(utils, "_provider_call", fake_provider_call)
    return calls


def _judge(prompt="the prompt", **overrides):
    kwargs = dict(system_prompt="judge", provider="openai", model="m", temperature=0.0)
    kwargs.update(overrides)
    return call_llm_judge(prompt, **kwargs)


# ── JudgeCache unit ──────────────────────────────────────────────────────────

class TestJudgeCacheUnit:
    def test_make_key_deterministic_and_sensitive(self):
        base = dict(provider="openai", model="m", system_prompt="s", prompt="p", temperature=0.0)
        key = JudgeCache.make_key(**base)
        assert key == JudgeCache.make_key(**base)
        assert key != JudgeCache.make_key(**{**base, "prompt": "other"})
        assert key != JudgeCache.make_key(**{**base, "temperature": 0.5})

    def test_put_get_persist(self, tmp_path):
        path = tmp_path / "jc.json"
        cache = JudgeCache(path)
        cache.put("k", {"pass": True})
        assert cache.get("k") == {"pass": True}
        assert JudgeCache(path).get("k") == {"pass": True}  # reload from disk

    def test_record_mode_get_returns_none(self, tmp_path):
        path = tmp_path / "jc.json"
        JudgeCache(path).put("k", {"pass": True})
        assert JudgeCache(path, mode="record").get("k") is None  # forces re-call

    def test_replay_mode_put_is_noop(self, tmp_path):
        path = tmp_path / "jc.json"
        cache = JudgeCache(path, mode="replay")
        cache.put("k", {"pass": True})
        assert cache.get("k") is None
        assert not path.exists()

    def test_invalid_mode_raises(self, tmp_path):
        with pytest.raises(ValueError):
            JudgeCache(tmp_path / "x.json", mode="bogus")


# ── integration with call_llm_judge ──────────────────────────────────────────

class TestCallLlmJudgeCaching:
    def test_no_cache_calls_provider_each_time(self, counting_provider):
        _judge()
        _judge()
        assert counting_provider["n"] == 2

    def test_auto_mode_caches_identical_calls(self, tmp_path, counting_provider):
        with use_judge_cache(tmp_path / "jc.json", mode="auto"):
            r1 = _judge()
            r2 = _judge()  # identical -> served from cache, no provider call
        assert counting_provider["n"] == 1
        assert r1 == r2 == {"pass": True, "reason": "ok", "score": 1.0}

    def test_auto_mode_distinct_prompts_call_twice(self, tmp_path, counting_provider):
        with use_judge_cache(tmp_path / "jc.json", mode="auto"):
            _judge("p1")
            _judge("p2")
        assert counting_provider["n"] == 2

    def test_replay_miss_raises_without_calling_model(self, tmp_path, counting_provider):
        with use_judge_cache(tmp_path / "jc.json", mode="replay"), pytest.raises(JudgeCacheMiss):
            _judge()
        assert counting_provider["n"] == 0

    def test_record_then_replay(self, tmp_path, counting_provider):
        path = tmp_path / "jc.json"
        with use_judge_cache(path, mode="record"):
            _judge()
        assert counting_provider["n"] == 1
        with use_judge_cache(path, mode="replay"):
            result = _judge()  # served from the recorded file
        assert counting_provider["n"] == 1
        assert result["pass"] is True

    def test_record_mode_always_calls(self, tmp_path, counting_provider):
        with use_judge_cache(tmp_path / "jc.json", mode="record"):
            _judge()
            _judge()  # record re-calls even when an entry exists
        assert counting_provider["n"] == 2

    def test_env_var_enables_cache(self, tmp_path, monkeypatch, counting_provider):
        monkeypatch.setenv(ENV_CACHE_PATH, str(tmp_path / "jc.json"))
        _judge()
        _judge()  # second call resolves the env cache and hits
        assert counting_provider["n"] == 1
