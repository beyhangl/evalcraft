# Example: LangGraph RAG Pipeline

A multi-step retrieval-augmented generation workflow built with LangGraph.
The pipeline answers questions about company policy documents through a
structured 5-node graph with a quality gate and hallucination check.

## Graph architecture

```
[rewrite_query] → [retrieve_docs] → [grade_relevance] → [generate_answer] → [check_hallucination]
                                                                                      │
                                                              ┌───────────────────────┘
                                                              │ (if not grounded, max 2 retries)
                                                              └→ [generate_answer]
```

**Nodes:**
1. `rewrite_query` — rewrites the user question for better retrieval precision
2. `retrieve_docs` — vector search over company policy KB (simulated)
3. `grade_relevance` — LLM filters irrelevant retrieved chunks
4. `generate_answer` — synthesizes answer with inline citations
5. `check_hallucination` — verifies answer is grounded in retrieved docs

## Scenario

**Company policy Q&A** — answers HR questions:
- "How many days a week can I work from home?" → cites Remote Work Policy v2.3
- "What equipment expenses can I claim?" → cites Equipment Policy v1.1

## Project layout

```
langgraph-workflow/
├── workflow.py                     # LangGraph graph definition
├── record_cassettes.py             # Capture live pipeline runs
├── requirements.txt
└── tests/
    ├── cassettes/
    │   ├── remote_work_policy.json  # 4 LLM calls, 5 node spans
    │   └── equipment_stipend.json
    └── test_rag_workflow.py         # Node-order + quality + budget tests
```

## Step-by-step setup

### 1. Install

```bash
cd examples/langgraph-workflow
pip install -r requirements.txt
```

### 2. Run tests (no API key needed)

```bash
pytest tests/ -v
```

Expected output:
```
tests/test_rag_workflow.py::TestNodeExecution::test_rewrite_query_node_executed[remote_work] PASSED
tests/test_rag_workflow.py::TestNodeExecution::test_node_order_rewrite_before_retrieve[remote_work] PASSED
tests/test_rag_workflow.py::TestAnswerQuality::test_remote_work_mentions_days PASSED
tests/test_rag_workflow.py::TestAnswerQuality::test_remote_work_includes_citation PASSED
...
22 passed in 0.34s
```

### 3. Record fresh cassettes

```bash
export OPENAI_API_KEY=sk-...
python record_cassettes.py
```

## Key concepts demonstrated

| Concept | Where |
|---------|-------|
| `LangGraphAdapter` auto-capture | `record_cassettes.py` |
| `SpanKind.AGENT_STEP` inspection | `TestNodeExecution` |
| Node order assertions | `test_node_order_rewrite_before_retrieve` |
| Conditional edge testing | `test_generate_before_hallucination_check` |
| Citation regex assertions | `test_remote_work_includes_citation` |
| `MockLLM.add_sequential_responses` | `test_full_pipeline_with_mocks` |
| Direct function testing (no graph) | `test_retrieve_docs_node_direct` |

## Node-level testing pattern

The cassettes capture each node as an `AGENT_STEP` span. You can assert
on individual nodes without re-running the full graph:

```python
from evalcraft import replay
from evalcraft.core.models import SpanKind

run = replay("tests/cassettes/remote_work_policy.json")

# Get all node names in execution order
node_names = [
    s.name for s in run.cassette.spans
    if s.kind == SpanKind.AGENT_STEP
]
print(node_names)
# ['node:rewrite_query', 'node:retrieve_docs', 'node:grade_relevance',
#  'node:generate_answer', 'node:check_hallucination']
```

## What to try

Override retrieval results to test the hallucination retry path:

```python
from evalcraft.replay.engine import ReplayEngine

engine = ReplayEngine("tests/cassettes/remote_work_policy.json")
# If you modify the cassette so is_grounded=False in check_hallucination,
# the conditional edge should trigger a regeneration loop
```
