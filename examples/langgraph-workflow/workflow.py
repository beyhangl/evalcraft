"""RAG pipeline workflow — a LangGraph multi-step retrieval-augmented generation pipeline.

The workflow answers user questions about company policy documents using a
retrieve-then-generate pattern with optional query rewriting and citation extraction.

Graph nodes:
    1. rewrite_query    — Clarifies ambiguous queries before retrieval
    2. retrieve_docs    — Retrieves relevant document chunks
    3. grade_relevance  — Filters out irrelevant chunks (quality gate)
    4. generate_answer  — Synthesizes an answer with citations
    5. check_hallucination — Verifies the answer is grounded in retrieved docs

This file contains workflow logic only. evalcraft instrumentation lives in tests/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, TypedDict


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class RAGState(TypedDict):
    """State passed between graph nodes."""
    question: str
    rewritten_question: str
    retrieved_docs: list[dict]
    graded_docs: list[dict]
    answer: str
    citations: list[str]
    is_grounded: bool
    iteration_count: int


# ---------------------------------------------------------------------------
# Fake knowledge base
# ---------------------------------------------------------------------------

_KNOWLEDGE_BASE = [
    {
        "id": "doc-001",
        "title": "Remote Work Policy v2.3",
        "content": (
            "Employees may work remotely up to 3 days per week with manager approval. "
            "Remote work requires a stable internet connection of at least 25 Mbps. "
            "Core hours are 10 AM to 3 PM in the employee's local timezone. "
            "All remote work must be logged in the HR portal by end of day."
        ),
        "score": 0.94,
    },
    {
        "id": "doc-002",
        "title": "Equipment Policy v1.1",
        "content": (
            "Remote employees receive a $800 annual equipment stipend. "
            "Approved purchases include monitors, keyboards, webcams, and ergonomic chairs. "
            "Receipts must be submitted within 30 days of purchase. "
            "Unused stipend does not roll over to the following year."
        ),
        "score": 0.87,
    },
    {
        "id": "doc-003",
        "title": "Travel and Expenses Policy v4.0",
        "content": (
            "Business travel requires pre-approval from your department head. "
            "Flight bookings must be made at least 14 days in advance for economy class. "
            "Hotel reimbursement is capped at $200/night in tier-1 cities and $150/night elsewhere. "
            "Meal allowance is $75/day for domestic travel, $100/day for international."
        ),
        "score": 0.71,
    },
    {
        "id": "doc-004",
        "title": "Data Security Policy v3.0",
        "content": (
            "All company data must be stored in approved cloud services (Google Workspace, AWS). "
            "USB storage devices are prohibited on company equipment. "
            "Password minimums: 12 characters, mix of uppercase, lowercase, numbers, and symbols. "
            "Multi-factor authentication is mandatory for all company accounts."
        ),
        "score": 0.65,
    },
]


def retrieve_documents(query: str, top_k: int = 3) -> list[dict]:
    """Retrieve top-k relevant documents for a query (simulated vector search)."""
    keywords = query.lower().split()
    scored = []
    for doc in _KNOWLEDGE_BASE:
        text = (doc["title"] + " " + doc["content"]).lower()
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            scored.append({**doc, "relevance": hits / len(keywords)})

    scored.sort(key=lambda d: d["relevance"], reverse=True)
    return scored[:top_k]


# ---------------------------------------------------------------------------
# Node functions (plain Python — no LangChain imports at module level)
# These are called by LangGraph nodes; in tests they can be called directly.
# ---------------------------------------------------------------------------

def rewrite_query_node(state: RAGState, llm: Any) -> RAGState:
    """Rewrite the user query for better retrieval precision."""
    from langchain_core.messages import HumanMessage

    response = llm.invoke([
        HumanMessage(content=(
            f"Rewrite this question to be more specific and searchable for a company policy database. "
            f"Output only the rewritten question, nothing else.\n\nOriginal: {state['question']}"
        ))
    ])
    return {**state, "rewritten_question": response.content.strip()}


def retrieve_docs_node(state: RAGState) -> RAGState:
    """Retrieve relevant policy documents."""
    query = state.get("rewritten_question") or state["question"]
    docs = retrieve_documents(query, top_k=3)
    return {**state, "retrieved_docs": docs}


def grade_relevance_node(state: RAGState, llm: Any) -> RAGState:
    """Grade each retrieved document for relevance to the question."""
    from langchain_core.messages import HumanMessage

    question = state.get("rewritten_question") or state["question"]
    graded = []

    for doc in state["retrieved_docs"]:
        response = llm.invoke([
            HumanMessage(content=(
                f"Is this document relevant to answering the question?\n\n"
                f"Question: {question}\n\n"
                f"Document: {doc['content']}\n\n"
                f"Answer with only 'yes' or 'no'."
            ))
        ])
        if response.content.strip().lower().startswith("yes"):
            graded.append(doc)

    return {**state, "graded_docs": graded}


def generate_answer_node(state: RAGState, llm: Any) -> RAGState:
    """Generate an answer from the graded documents."""
    from langchain_core.messages import HumanMessage

    docs_text = "\n\n".join(
        f"[{d['id']}] {d['title']}: {d['content']}"
        for d in state["graded_docs"]
    )

    response = llm.invoke([
        HumanMessage(content=(
            f"Answer the following question using ONLY the provided documents. "
            f"Include citation IDs (e.g., [doc-001]) for each claim.\n\n"
            f"Question: {state['question']}\n\n"
            f"Documents:\n{docs_text}"
        ))
    ])

    answer = response.content.strip()
    import re
    citations = re.findall(r"\[doc-\d+\]", answer)

    return {**state, "answer": answer, "citations": list(set(citations))}


def check_hallucination_node(state: RAGState, llm: Any) -> RAGState:
    """Verify the answer is grounded in the retrieved documents."""
    from langchain_core.messages import HumanMessage

    docs_text = "\n\n".join(d["content"] for d in state["graded_docs"])

    response = llm.invoke([
        HumanMessage(content=(
            f"Is the following answer fully supported by the provided documents? "
            f"Answer with 'yes' or 'no' only.\n\n"
            f"Answer: {state['answer']}\n\n"
            f"Documents:\n{docs_text}"
        ))
    ])

    is_grounded = response.content.strip().lower().startswith("yes")
    return {**state, "is_grounded": is_grounded}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

from typing import Any


def build_rag_graph(llm: Any) -> Any:
    """Build and compile the RAG workflow graph.

    Args:
        llm: A LangChain-compatible chat model (e.g., ChatOpenAI).

    Returns:
        A compiled LangGraph CompiledStateGraph.
    """
    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        raise ImportError(
            "langgraph is required for this example. "
            "Install it with: pip install -r requirements.txt"
        )

    def _rewrite(state: RAGState) -> RAGState:
        return rewrite_query_node(state, llm)

    def _retrieve(state: RAGState) -> RAGState:
        return retrieve_docs_node(state)

    def _grade(state: RAGState) -> RAGState:
        return grade_relevance_node(state, llm)

    def _generate(state: RAGState) -> RAGState:
        return generate_answer_node(state, llm)

    def _check(state: RAGState) -> RAGState:
        return check_hallucination_node(state, llm)

    def _should_regenerate(state: RAGState) -> str:
        """Conditional edge: regenerate if not grounded (max 2 iterations)."""
        if not state.get("is_grounded", True) and state.get("iteration_count", 0) < 2:
            return "generate_answer"
        return END

    graph = StateGraph(RAGState)
    graph.add_node("rewrite_query", _rewrite)
    graph.add_node("retrieve_docs", _retrieve)
    graph.add_node("grade_relevance", _grade)
    graph.add_node("generate_answer", _generate)
    graph.add_node("check_hallucination", _check)

    graph.set_entry_point("rewrite_query")
    graph.add_edge("rewrite_query", "retrieve_docs")
    graph.add_edge("retrieve_docs", "grade_relevance")
    graph.add_edge("grade_relevance", "generate_answer")
    graph.add_edge("generate_answer", "check_hallucination")
    graph.add_conditional_edges("check_hallucination", _should_regenerate)

    return graph.compile()
