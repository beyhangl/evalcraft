"""Tests for cassette provenance metadata (issue #19).

Provenance records *what* a cassette was captured against (models, prompt hash,
SDK/Python versions, record time) so staleness can be judged on real signal
rather than file age. Must be back-compatible with provenance-less cassettes.
"""

from evalcraft import CaptureContext
from evalcraft.core.models import Cassette, Provenance, Span, SpanKind, TokenUsage


def _cassette_with_llm() -> Cassette:
    c = Cassette(name="prov", agent_name="a")
    c.input_text = "What is 2+2?"
    c.add_span(
        Span(
            kind=SpanKind.LLM_RESPONSE,
            name="llm",
            model="gpt-4.1-mini",
            input="What is 2+2?",
            output="4",
            token_usage=TokenUsage(prompt_tokens=5, completion_tokens=1, total_tokens=6),
            cost_usd=0.0001,
        )
    )
    return c


class TestCaptureProvenance:
    def test_sets_expected_fields(self):
        c = _cassette_with_llm()
        prov = c.capture_provenance()
        assert prov is c.provenance
        assert prov.recorded_at > 0
        assert prov.python_version  # e.g. "3.10.9"
        assert prov.models == ["gpt-4.1-mini"]
        assert len(prov.prompt_hash) == 16

    def test_prompt_hash_is_deterministic_for_same_content(self):
        c = _cassette_with_llm()
        first = c.capture_provenance().prompt_hash
        second = c.capture_provenance().prompt_hash
        assert first == second

    def test_prompt_hash_changes_with_input(self):
        c1 = _cassette_with_llm()
        c2 = _cassette_with_llm()
        c2.spans[0].input = "What is 3+3?"
        assert c1.capture_provenance().prompt_hash != c2.capture_provenance().prompt_hash

    def test_dedupes_and_sorts_models(self):
        c = _cassette_with_llm()
        c.add_span(
            Span(kind=SpanKind.LLM_RESPONSE, model="claude-haiku-4-5", input="x", output="y")
        )
        c.add_span(
            Span(kind=SpanKind.LLM_RESPONSE, model="gpt-4.1-mini", input="z", output="w")
        )
        prov = c.capture_provenance()
        assert prov.models == ["claude-haiku-4-5", "gpt-4.1-mini"]


class TestProvenanceRoundTrip:
    def test_to_from_dict_preserves_provenance(self):
        c = _cassette_with_llm()
        c.capture_provenance()
        restored = Cassette.from_dict(c.to_dict())
        assert restored.provenance is not None
        assert restored.provenance.models == ["gpt-4.1-mini"]
        assert restored.provenance.prompt_hash == c.provenance.prompt_hash
        assert restored.provenance.python_version == c.provenance.python_version

    def test_save_load_file(self, tmp_path):
        c = _cassette_with_llm()
        c.capture_provenance()
        path = tmp_path / "c.json"
        c.save(path)
        restored = Cassette.load(path)
        assert restored.provenance is not None
        assert restored.provenance.prompt_hash == c.provenance.prompt_hash

    def test_provenance_does_not_change_fingerprint(self):
        c = _cassette_with_llm()
        fp_before = c.compute_fingerprint()
        c.capture_provenance()
        fp_after = c.compute_fingerprint()
        assert fp_before == fp_after  # provenance lives outside spans

    def test_provenance_dataclass_roundtrip(self):
        p = Provenance(
            recorded_at=123.0,
            sdk_version="0.1.0",
            python_version="3.10.9",
            models=["gpt-4.1-mini"],
            prompt_hash="abc123",
        )
        assert Provenance.from_dict(p.to_dict()) == p


class TestBackCompat:
    def test_handbuilt_cassette_has_no_provenance(self):
        c = _cassette_with_llm()
        assert c.provenance is None
        assert c.to_dict()["cassette"]["provenance"] is None

    def test_legacy_dict_without_provenance_loads(self):
        legacy = {
            "evalcraft_version": "0.1.0",
            "cassette": {
                "id": "abc", "name": "legacy", "version": "1.0",
                "created_at": 0.0, "agent_name": "", "framework": "",
                "input_text": "", "output_text": "",
                "total_tokens": 0, "total_cost_usd": 0.0, "total_duration_ms": 0.0,
                "llm_call_count": 0, "tool_call_count": 0,
                "fingerprint": "", "metadata": {},
            },
            "spans": [],
        }
        c = Cassette.from_dict(legacy)
        assert c.provenance is None
        assert c.name == "legacy"


class TestCaptureContextProvenance:
    def test_context_sets_provenance_on_exit(self):
        with CaptureContext(name="ctx") as ctx:
            ctx.record_input("hi")
            ctx.record_llm_call(
                model="gpt-4.1-mini", input="hi", output="hello",
                prompt_tokens=2, completion_tokens=1, cost_usd=0.0,
            )
            ctx.record_output("hello")
        assert ctx.cassette.provenance is not None
        assert "gpt-4.1-mini" in ctx.cassette.provenance.models
        assert ctx.cassette.provenance.python_version
