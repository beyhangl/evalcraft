"""RAG evaluation scorers — specialized metrics for Retrieval-Augmented Generation.

Evaluates the three core dimensions of RAG quality:

- **Faithfulness**: Does the output contradict or fabricate beyond the retrieved context?
- **Context Relevance**: Are the retrieved chunks actually relevant to the query?
- **Answer Relevance**: Does the answer address the original question?

These are modeled after RAGAS (ACL 2024) and work reference-free — no ground
truth needed, only the query, retrieved context, and agent output.

Usage::

    from evalcraft.eval.rag_scorers import (
        assert_faithfulness,
        assert_context_relevance,
        assert_answer_relevance,
    )

    run = replay("tests/cassettes/rag_agent.json")
    contexts = ["Paris has a population of 2.1 million...", "The Eiffel Tower..."]

    assert assert_faithfulness(run, contexts=contexts).passed
    assert assert_context_relevance(run, query="Tell me about Paris", contexts=contexts).passed
    assert assert_answer_relevance(run, query="Tell me about Paris").passed
"""

from __future__ import annotations

from typing import Any

from evalcraft.core.models import (
    AgentRun,
    AssertionResult,
    Cassette,
)
from evalcraft.eval._utils import get_cassette, call_llm_judge, normalize_pass_key


_RAG_SYSTEM_PROMPT = (
    "You are a RAG evaluation judge. You evaluate retrieval-augmented "
    "generation quality. Respond ONLY with a JSON object: "
    '{"pass": true/false, "score": 0.0-1.0, "reason": "brief explanation", '
    '"claims": [{"claim": "...", "supported": true/false}]}'
)


def _call_rag_judge(
    prompt: str,
    *,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """Call an LLM judge for RAG evaluation and parse the structured response."""
    result = call_llm_judge(
        prompt,
        system_prompt=_RAG_SYSTEM_PROMPT,
        provider=provider,
        model=model,
        api_key=api_key,
        temperature=temperature,
    )
    result = normalize_pass_key(result)
    result.setdefault("claims", [])
    return result


# ---------------------------------------------------------------------------
# Public scorers
# ---------------------------------------------------------------------------

def assert_faithfulness(
    cassette: Cassette | AgentRun,
    contexts: list[str],
    *,
    threshold: float = 0.8,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> AssertionResult:
    """Assert that the agent output is faithful to the retrieved contexts.

    Decomposes the output into atomic claims, then checks each claim against
    the provided contexts.  The faithfulness score is the fraction of claims
    that are supported by the context.

    Args:
        cassette: The cassette or agent run to evaluate.
        contexts: List of retrieved context strings (chunks/passages).
        threshold: Minimum faithfulness score to pass (0.0-1.0, default 0.8).
        provider: LLM provider — ``"openai"`` (default) or ``"anthropic"``.
        model: Override the judge model.
        api_key: Optional API key override.
    """
    c = get_cassette(cassette)
    output = c.output_text

    if not output:
        return AssertionResult(
            name="assert_faithfulness",
            passed=False,
            expected=f"faithfulness >= {threshold}",
            actual="<empty output>",
            message="Agent produced no output to evaluate.",
        )

    if not contexts:
        return AssertionResult(
            name="assert_faithfulness",
            passed=False,
            expected="contexts provided",
            actual="<no contexts>",
            message="No contexts provided for faithfulness evaluation.",
        )

    context_block = "\n\n---\n\n".join(
        f"Context {i + 1}:\n{ctx}" for i, ctx in enumerate(contexts)
    )

    prompt = (
        f"## Retrieved Contexts\n{context_block}\n\n"
        f"## Agent Output\n{output}\n\n"
        "## Task\n"
        "1. Extract all factual claims from the agent output.\n"
        "2. For each claim, determine if it is supported by the retrieved contexts.\n"
        "3. A claim is 'supported' if the contexts contain information that confirms it.\n"
        "4. A claim is 'unsupported' if it contradicts the contexts or adds information "
        "not present in them.\n"
        "5. Calculate the faithfulness score as: (supported claims) / (total claims).\n"
        f"6. Pass if the score is >= {threshold}."
    )

    result = _call_rag_judge(prompt, provider=provider, model=model, api_key=api_key)
    score = float(result.get("score", 0.0))
    passed = score >= threshold

    claims = result.get("claims", [])
    supported = sum(1 for cl in claims if cl.get("supported", False))
    total = len(claims) if claims else 0
    detail = f"{supported}/{total} claims supported" if total > 0 else ""

    return AssertionResult(
        name="assert_faithfulness",
        passed=passed,
        expected=f"faithfulness >= {threshold}",
        actual=f"{score:.2f}" + (f" ({detail})" if detail else ""),
        message=result.get("reason", "") if not passed else "",
    )


def assert_context_relevance(
    cassette: Cassette | AgentRun,
    query: str,
    contexts: list[str],
    *,
    threshold: float = 0.7,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> AssertionResult:
    """Assert that the retrieved contexts are relevant to the query.

    Evaluates each context chunk for relevance to the original query.
    The score is the fraction of contexts that are relevant.

    Args:
        cassette: The cassette or agent run (used for metadata; query/contexts
                  are provided explicitly).
        query: The original user query.
        contexts: List of retrieved context strings.
        threshold: Minimum context relevance score to pass (0.0-1.0, default 0.7).
        provider: LLM provider.
        model: Override the judge model.
        api_key: Optional API key override.
    """
    get_cassette(cassette)  # Validate input type

    if not contexts:
        return AssertionResult(
            name="assert_context_relevance",
            passed=False,
            expected="contexts provided",
            actual="<no contexts>",
            message="No contexts provided for relevance evaluation.",
        )

    context_block = "\n\n---\n\n".join(
        f"Context {i + 1}:\n{ctx}" for i, ctx in enumerate(contexts)
    )

    prompt = (
        f"## User Query\n{query}\n\n"
        f"## Retrieved Contexts\n{context_block}\n\n"
        "## Task\n"
        "1. For each context, determine if it is relevant to answering the user query.\n"
        "2. A context is 'relevant' if it contains information that could help answer "
        "the query, even if only partially.\n"
        "3. A context is 'irrelevant' if it has no useful information for the query.\n"
        "4. Calculate the score as: (relevant contexts) / (total contexts).\n"
        f"5. Pass if the score is >= {threshold}.\n"
        "6. In the 'claims' array, list each context with 'claim' as a summary and "
        "'supported' as whether it is relevant."
    )

    result = _call_rag_judge(prompt, provider=provider, model=model, api_key=api_key)
    score = float(result.get("score", 0.0))
    passed = score >= threshold

    claims = result.get("claims", [])
    relevant = sum(1 for cl in claims if cl.get("supported", False))
    total = len(claims) if claims else len(contexts)
    detail = f"{relevant}/{total} contexts relevant"

    return AssertionResult(
        name="assert_context_relevance",
        passed=passed,
        expected=f"context_relevance >= {threshold}",
        actual=f"{score:.2f} ({detail})",
        message=result.get("reason", "") if not passed else "",
    )


def assert_answer_relevance(
    cassette: Cassette | AgentRun,
    query: str,
    *,
    threshold: float = 0.7,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> AssertionResult:
    """Assert that the agent output is relevant to the original query.

    Checks whether the answer actually addresses the question asked, rather
    than being off-topic or incomplete.

    Args:
        cassette: The cassette or agent run to evaluate.
        query: The original user query.
        threshold: Minimum answer relevance score to pass (0.0-1.0, default 0.7).
        provider: LLM provider.
        model: Override the judge model.
        api_key: Optional API key override.
    """
    c = get_cassette(cassette)
    output = c.output_text

    if not output:
        return AssertionResult(
            name="assert_answer_relevance",
            passed=False,
            expected=f"answer_relevance >= {threshold}",
            actual="<empty output>",
            message="Agent produced no output to evaluate.",
        )

    prompt = (
        f"## User Query\n{query}\n\n"
        f"## Agent Output\n{output}\n\n"
        "## Task\n"
        "1. Determine how well the agent output answers the user query.\n"
        "2. Consider: Does the output address the core question? Is it on-topic? "
        "Does it provide the type of information the user was looking for?\n"
        "3. Score from 0.0 (completely irrelevant) to 1.0 (perfectly relevant).\n"
        f"4. Pass if the score is >= {threshold}."
    )

    result = _call_rag_judge(prompt, provider=provider, model=model, api_key=api_key)
    score = float(result.get("score", 0.0))
    passed = score >= threshold

    return AssertionResult(
        name="assert_answer_relevance",
        passed=passed,
        expected=f"answer_relevance >= {threshold}",
        actual=f"{score:.2f}",
        message=result.get("reason", "") if not passed else "",
    )


def assert_context_recall(
    cassette: Cassette | AgentRun,
    query: str,
    contexts: list[str],
    ground_truth: str,
    *,
    threshold: float = 0.7,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> AssertionResult:
    """Assert that the retrieved contexts contain the information needed to answer correctly.

    Unlike the other RAG scorers, this one requires a ground truth answer to
    check whether the retrieval step fetched sufficient context.

    Args:
        cassette: The cassette or agent run to evaluate.
        query: The original user query.
        contexts: List of retrieved context strings.
        ground_truth: The known-correct answer to compare against.
        threshold: Minimum recall score to pass (0.0-1.0, default 0.7).
        provider: LLM provider.
        model: Override the judge model.
        api_key: Optional API key override.
    """
    get_cassette(cassette)  # Validate input type

    if not contexts:
        return AssertionResult(
            name="assert_context_recall",
            passed=False,
            expected="contexts provided",
            actual="<no contexts>",
            message="No contexts provided for recall evaluation.",
        )

    context_block = "\n\n---\n\n".join(
        f"Context {i + 1}:\n{ctx}" for i, ctx in enumerate(contexts)
    )

    prompt = (
        f"## User Query\n{query}\n\n"
        f"## Ground Truth Answer\n{ground_truth}\n\n"
        f"## Retrieved Contexts\n{context_block}\n\n"
        "## Task\n"
        "1. Extract the key facts from the ground truth answer.\n"
        "2. For each fact, check if it can be found in the retrieved contexts.\n"
        "3. Calculate the recall score as: (facts found in contexts) / (total facts).\n"
        f"4. Pass if the score is >= {threshold}.\n"
        "5. In 'claims', list each fact with 'supported' indicating if it was found."
    )

    result = _call_rag_judge(prompt, provider=provider, model=model, api_key=api_key)
    score = float(result.get("score", 0.0))
    passed = score >= threshold

    claims = result.get("claims", [])
    found = sum(1 for cl in claims if cl.get("supported", False))
    total = len(claims) if claims else 0
    detail = f"{found}/{total} facts recalled" if total > 0 else ""

    return AssertionResult(
        name="assert_context_recall",
        passed=passed,
        expected=f"context_recall >= {threshold}",
        actual=f"{score:.2f}" + (f" ({detail})" if detail else ""),
        message=result.get("reason", "") if not passed else "",
    )
