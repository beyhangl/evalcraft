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

- :class:`AutoGenAdapter` — patches AutoGen's ``ConversableAgent`` to capture
  inter-agent messages, LLM responses, and function / tool call executions.

- :class:`LlamaIndexAdapter` — hooks into LlamaIndex's callback system to
  capture queries, retrieval, LLM synthesis, and function calls.

- :class:`GeminiAdapter` — patches the Google Gemini SDK to record every
  ``GenerativeModel.generate_content()`` call (sync and async).

- :class:`PydanticAIAdapter` — patches the Pydantic AI ``Agent`` class to
  record every ``run()`` and ``run_sync()`` call, including tool calls.

Usage::

    from evalcraft.adapters import (
        OpenAIAdapter, AnthropicAdapter, LangGraphAdapter, CrewAIAdapter,
        AutoGenAdapter, LlamaIndexAdapter,
    )
"""

from evalcraft.adapters.anthropic_adapter import AnthropicAdapter
from evalcraft.adapters.autogen_adapter import AutoGenAdapter
from evalcraft.adapters.crewai_adapter import CrewAIAdapter
from evalcraft.adapters.langgraph_adapter import LangGraphAdapter
from evalcraft.adapters.llamaindex_adapter import LlamaIndexAdapter
from evalcraft.adapters.openai_adapter import OpenAIAdapter
from evalcraft.adapters.gemini_adapter import GeminiAdapter
from evalcraft.adapters.pydantic_ai_adapter import PydanticAIAdapter

__all__ = [
    "OpenAIAdapter",
    "AnthropicAdapter",
    "LangGraphAdapter",
    "CrewAIAdapter",
    "AutoGenAdapter",
    "LlamaIndexAdapter",
    "GeminiAdapter",
    "PydanticAIAdapter",
]
