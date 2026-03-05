"""Framework adapters — auto-capture LLM and agent calls into evalcraft spans.

Available adapters:

- :class:`OpenAIAdapter` — patches the OpenAI Python SDK to record every
  ``chat.completions.create()`` call (sync and async).

- :class:`LangGraphAdapter` — injects a LangChain callback handler into a
  compiled LangGraph graph to record node executions, LLM calls, and tool
  calls.

Usage::

    from evalcraft.adapters import OpenAIAdapter, LangGraphAdapter
"""

from evalcraft.adapters.langgraph_adapter import LangGraphAdapter
from evalcraft.adapters.openai_adapter import OpenAIAdapter

__all__ = ["OpenAIAdapter", "LangGraphAdapter"]
