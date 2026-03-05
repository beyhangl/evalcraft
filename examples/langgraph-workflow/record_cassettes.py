"""record_cassettes.py — Capture LangGraph RAG pipeline runs into cassettes.

Usage:
    OPENAI_API_KEY=sk-... python record_cassettes.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from langchain_openai import ChatOpenAI
    from langgraph.graph import StateGraph
except ImportError:
    sys.exit(
        "langgraph and langchain-openai are required.\n"
        "Run: pip install -r requirements.txt"
    )

from evalcraft import CaptureContext
from evalcraft.adapters import LangGraphAdapter
from workflow import build_rag_graph, RAGState


CASSETTES_DIR = Path(__file__).parent / "tests" / "cassettes"
CASSETTES_DIR.mkdir(parents=True, exist_ok=True)


def record_query(scenario_name: str, question: str, llm: Any) -> None:
    print(f"\n--- Recording: {scenario_name} ---")
    print(f"Question: {question}")

    cassette_path = CASSETTES_DIR / f"{scenario_name}.json"
    graph = build_rag_graph(llm)

    initial_state: RAGState = {
        "question": question,
        "rewritten_question": "",
        "retrieved_docs": [],
        "graded_docs": [],
        "answer": "",
        "citations": [],
        "is_grounded": False,
        "iteration_count": 0,
    }

    with CaptureContext(
        name=scenario_name,
        agent_name="rag_pipeline",
        framework="langgraph",
        save_path=cassette_path,
    ) as ctx:
        ctx.record_input(question)

        with LangGraphAdapter(graph):
            result = graph.invoke(initial_state)

        ctx.record_output(result["answer"])

    c = ctx.cassette
    print(f"Answer: {result['answer'][:100]}...")
    print(f"Citations: {result['citations']}")
    print(f"Grounded: {result['is_grounded']}")
    print(f"Spans:  {len(c.spans)}")
    print(f"Tokens: {c.total_tokens}")
    print(f"Cost:   ${c.total_cost_usd:.5f}")
    print(f"Saved:  {cassette_path}")


def main() -> None:
    from typing import Any
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("Set OPENAI_API_KEY before recording.")

    llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0)

    scenarios = [
        ("remote_work_policy", "How many days a week can I work from home?"),
        ("equipment_stipend", "What equipment expenses can I claim and how much?"),
        ("travel_reimbursement", "What is the hotel reimbursement cap for international travel?"),
    ]

    for name, question in scenarios:
        record_query(name, question, llm)

    print(f"\nAll cassettes saved to {CASSETTES_DIR}")


if __name__ == "__main__":
    main()
