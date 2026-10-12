"""Local research probes for pactrun at bfcaf8a; no network, SDK keys, or real tools.

Run with:
  /private/tmp/agent-project-research-venv/bin/python verify_local_findings.py

These reproduce observed limits of this checkout, rather than validating any
external service or claiming exploitable access to customer systems.
"""
import asyncio
import importlib
import json
import time
from types import SimpleNamespace

from pactrun import wrap
from pactrun.core.enums import EventKind
from pactrun.core.errors import ViolationError
from pactrun.core.models import Event, SessionState
from pactrun.predicates.consent import consent_token_required, mint_consent_token


def responses_bypass():
    calls = []

    def local_responses_create(**kwargs):
        calls.append(kwargs)
        return "local fake response"

    class DummyOpenAI:
        def __init__(self):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: None)
            )
            self.responses = SimpleNamespace(create=local_responses_create)

    guarded = wrap(DummyOpenAI(), max_cost=0)
    result = guarded.responses.create(model="local-demo", input="hello")
    assert result == "local fake response"
    assert len(calls) == 1
    assert guarded.session.state.total_llm_calls == 0
    return {
        "fake_provider_calls_with_zero_budget": len(calls),
        "recorded_calls": guarded.session.state.total_llm_calls,
    }


async def concurrent_budget_admission():
    wrapper_module = importlib.import_module("pactrun.wrap")
    old_estimate = wrapper_module._estimate_worstcase_cost
    wrapper_module._estimate_worstcase_cost = lambda kwargs, n: (0.75, "fixed-local-probe")
    entered = []
    release = asyncio.Event()

    async def local_create(**kwargs):
        entered.append(kwargs)
        if len(entered) == 2:
            release.set()
        await release.wait()
        return SimpleNamespace(cost=0.75)

    class AsyncDummyOpenAI:
        def __init__(self):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=local_create)
            )

    try:
        guarded = wrap(AsyncDummyOpenAI(), max_cost=1.0)
        guarded._record = lambda kwargs, response: guarded.session.emit_llm_response(
            model="local-demo", output="ok", cost=response.cost
        )
        results = await asyncio.wait_for(
            asyncio.gather(
                guarded.chat.completions.create(model="local-demo"),
                guarded.chat.completions.create(model="local-demo"),
                return_exceptions=True,
            ),
            timeout=3,
        )
        post_call_violations = sum(isinstance(r, ViolationError) for r in results)
        assert len(entered) == 2
        assert guarded.session.state.total_cost_usd == 1.5
        assert post_call_violations == 1
        return {
            "budget": 1.0,
            "fake_provider_calls_started": len(entered),
            "fixed_cost_per_call": 0.75,
            "cost_recorded_after_both_calls": guarded.session.state.total_cost_usd,
            "post_call_violations": post_call_violations,
            "scope": "isolates missing in-flight reservation; does not test price estimation",
        }
    finally:
        wrapper_module._estimate_worstcase_cost = old_estimate


def approval_metadata():
    args = {"customer_id": "synthetic-customer", "amount_minor": 2500}
    fields = ["customer_id", "amount_minor"]
    token = mint_consent_token(
        "refund",
        args=args,
        bind_args=fields,
        secret="synthetic-local-secret",
        issued_at=time.time() - 1000,
    )
    checker = consent_token_required(
        "refund", bind_args=fields, secret="synthetic-local-secret", max_age_s=300
    )
    state = SessionState()

    def present(tok):
        return checker(
            Event(kind=EventKind.TOOL_CALL, tool_name="refund", tool_args=args,
                  metadata={"user_consent": tok}),
            state,
        ).passed

    old_rejected = not present(token)
    altered = {**token, "issued_at": time.time()}
    timestamp_only_accepted = present(altered)
    accepted_again = present(altered)
    assert old_rejected
    assert timestamp_only_accepted and accepted_again
    assert token["sig"] == altered["sig"]
    return {
        "old_token_rejected": old_rejected,
        "timestamp_only_edit_accepted_with_same_signature": timestamp_only_accepted,
        "same_action_args_token_accepted_again": accepted_again,
        "scope": "metadata must be alterable; other host controls may mitigate",
    }


if __name__ == "__main__":
    print(json.dumps({
        "responses_bypass": responses_bypass(),
        "concurrent_budget": asyncio.run(concurrent_budget_admission()),
        "approval_metadata": approval_metadata(),
    }, indent=2))
