"""Framework adapters — auto-capture LLM and agent calls into evalcraft spans.

Available adapters:

- :class:`OpenAIAdapter` — patches the OpenAI Python SDK to record every
  ``chat.completions.create()`` call (sync and async).

- :class:`AnthropicAdapter` — patches the Anthropic Python SDK to record every
  ``messages.create()`` call (sync and async).

- :class:`LangGraphAdapter` — injects a LangChain callback handler into a
  compiled LangGraph graph to record node executions, LLM calls, and tool
  calls.

- :class:`CrewAIAdapter` — instruments a CrewAI ``Crew`` to capture
  ``kickoff()`` timing, agent tool calls, task completions, and
  inter-agent delegations.

Usage::

    from evalcraft.adapters import OpenAIAdapter, AnthropicAdapter, LangGraphAdapter, CrewAIAdapter
"""

from evalcraft.adapters.anthropic_adapter import AnthropicAdapter
from evalcraft.adapters.crewai_adapter import CrewAIAdapter
from evalcraft.adapters.langgraph_adapter import LangGraphAdapter
from evalcraft.adapters.openai_adapter import OpenAIAdapter

__all__ = ["OpenAIAdapter", "AnthropicAdapter", "LangGraphAdapter", "CrewAIAdapter"]
