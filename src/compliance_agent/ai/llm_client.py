"""LLM client adapter.

The codebase was originally built against the Anthropic SDK. This module
provides a uniform `make_client()` that returns something matching the
Anthropic `.messages.create()` / `.messages.parse()` shape, with the
backend chosen at runtime:

  - ANTHROPIC_API_KEY set            → uses anthropic SDK directly (no change)
  - OPENROUTER_API_KEY set           → wraps the OpenAI SDK pointed at
                                       https://openrouter.ai/api/v1 with a
                                       shim that exposes Anthropic-style
                                       message + tool surfaces

Call sites stay the same:

    from compliance_agent.ai.llm_client import make_client
    client = make_client()
    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        system="...",
        messages=[{"role": "user", "content": "..."}],
        tools=[...],            # optional
    )

The model string is passed through unchanged for the Anthropic path. For
the OpenRouter path it's remapped via OPENROUTER_MODEL (default
``anthropic/claude-sonnet-4-5``) since OpenRouter uses the provider/model
naming convention.

Limitations of the OpenRouter shim:
  - Streaming is not supported (the running app doesn't use it).
  - Anthropic-only kwargs (`thinking`, `output_config`, cache markers in
    `system`) are silently dropped.
  - Multi-turn tool flows that round-trip Anthropic content blocks
    (`tool_use`, `tool_result`) work for plain user/assistant text but
    serialise non-text blocks as a short placeholder when going to
    OpenAI's message format.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Public predicate
# ---------------------------------------------------------------------------
def ai_available() -> bool:
    """True when the master live-mode flag is on AND we have a usable key
    for at least one backend."""
    if os.environ.get("COMPLIANCE_AGENT_LIVE") != "1":
        return False
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
    )


def active_backend() -> str:
    """Returns 'openrouter' or 'anthropic' or 'mock'. Useful for log lines
    and the /api/system/info debug payload."""
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "mock"


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------
def make_client():
    """Return an object exposing `.messages.create()` and `.messages.parse()`.
    Picks the right backend based on which env var is set; OpenRouter wins
    when both are present (cheaper for most users)."""
    if os.environ.get("OPENROUTER_API_KEY"):
        return _OpenRouterClient()
    import anthropic
    return anthropic.Anthropic()


def resolve_model(model: str) -> str:
    """Map our internal model string to whatever the active backend wants.

    Anthropic path: passes through unchanged (e.g. claude-opus-4-7).
    OpenRouter path: returns OPENROUTER_MODEL if set, else a sensible
    default (anthropic/claude-sonnet-4-5 — fast + cheap for tool flows).
    """
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ.get(
            "OPENROUTER_MODEL",
            "anthropic/claude-sonnet-4-5",
        )
    return model


# ---------------------------------------------------------------------------
# OpenRouter shim
# ---------------------------------------------------------------------------
class _OpenRouterClient:
    def __init__(self) -> None:
        from openai import OpenAI

        self._openai = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
            default_headers={
                # OpenRouter recommends sending these for analytics. Skipped
                # if the env var is missing — they're optional.
                "HTTP-Referer": os.environ.get("COMPLIANCE_BASE_URL", "")
                or "https://github.com/anthropics/aspora-compliance",
                "X-Title": "Aspora Compliance OS",
            },
        )
        self.messages = _Messages(self._openai)


class _Messages:
    def __init__(self, openai_client) -> None:
        self._openai = openai_client

    # ------------------------------------------------------------------
    # client.messages.create(...) — text generation, with optional tools
    # ------------------------------------------------------------------
    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list,
        system: Any = None,
        tools: Optional[list] = None,
        tool_choice: Any = None,
        # Anthropic-only kwargs — accept + drop.
        thinking: Any = None,
        output_config: Any = None,
        **_extra: Any,
    ):
        oa_messages = _anth_to_openai_messages(system, messages)
        kw: dict[str, Any] = {
            "model": resolve_model(model),
            "messages": oa_messages,
            "max_tokens": max_tokens,
        }
        if tools:
            kw["tools"] = [_anth_tool_to_openai(t) for t in tools]
            if tool_choice is not None:
                kw["tool_choice"] = _anth_tool_choice_to_openai(tool_choice)
        completion = self._openai.chat.completions.create(**kw)
        return _AnthropicShapedResponse(completion)

    # ------------------------------------------------------------------
    # client.messages.parse(...) — structured output via Pydantic model
    # ------------------------------------------------------------------
    def parse(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list,
        system: Any = None,
        output_format: Any = None,
        thinking: Any = None,
        output_config: Any = None,
        **_extra: Any,
    ):
        oa_messages = _anth_to_openai_messages(system, messages)
        completion = self._openai.beta.chat.completions.parse(
            model=resolve_model(model),
            messages=oa_messages,
            max_tokens=max_tokens,
            response_format=output_format,
        )
        return _AnthropicShapedParseResponse(completion)


# ---------------------------------------------------------------------------
# Message + tool conversion
# ---------------------------------------------------------------------------
def _anth_to_openai_messages(system: Any, messages: list) -> list[dict]:
    """Flatten Anthropic-style inputs into the OpenAI chat format."""
    sys_text: Optional[str] = None
    if isinstance(system, str):
        sys_text = system
    elif isinstance(system, list):
        # Anthropic accepts `[{type: text, text: "...", cache_control: {...}}]`
        # for prompt caching. Collapse to one string for OpenAI.
        sys_text = "\n\n".join(
            b.get("text", "")
            for b in system
            if isinstance(b, dict) and b.get("type") == "text"
        )

    out: list[dict] = []
    if sys_text:
        out.append({"role": "system", "content": sys_text})

    for m in messages:
        if not isinstance(m, dict):
            out.append(m)
            continue
        role = m.get("role")
        content = m.get("content")

        # Anthropic content can be a string OR a list of blocks. The
        # block kinds we see in this codebase: text, tool_use, tool_result.
        if isinstance(content, list):
            text_parts: list[str] = []
            tool_calls: list[dict] = []
            tool_results: list[dict] = []
            for block in content:
                if not isinstance(block, dict):
                    text_parts.append(str(block))
                    continue
                bt = block.get("type")
                if bt == "text":
                    text_parts.append(block.get("text", ""))
                elif bt == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": json.dumps(block.get("input") or {}),
                            },
                        }
                    )
                elif bt == "tool_result":
                    tool_results.append(
                        {
                            "tool_call_id": block.get("tool_use_id", ""),
                            "content": _stringify(block.get("content")),
                        }
                    )
            # The assistant turn may have both text and tool calls.
            if role == "assistant":
                msg: dict = {"role": "assistant"}
                if text_parts:
                    msg["content"] = "\n".join(p for p in text_parts if p)
                if tool_calls:
                    msg["tool_calls"] = tool_calls
                if "content" not in msg and "tool_calls" not in msg:
                    msg["content"] = ""
                out.append(msg)
            # A user turn carrying tool_result blocks becomes one OpenAI
            # `tool` message per result.
            elif role == "user" and tool_results:
                for tr in tool_results:
                    out.append({"role": "tool", **tr})
                # Surface any plain user text that came alongside.
                if text_parts:
                    out.append({"role": "user", "content": "\n".join(text_parts)})
            else:
                out.append({"role": role, "content": "\n".join(text_parts)})
        else:
            out.append({"role": role, "content": content})
    return out


def _stringify(c: Any) -> str:
    if c is None:
        return ""
    if isinstance(c, str):
        return c
    return json.dumps(c)


def _anth_tool_to_openai(t: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("input_schema", {"type": "object"}),
        },
    }


def _anth_tool_choice_to_openai(tc: Any) -> Any:
    if isinstance(tc, dict):
        if tc.get("type") == "tool" and tc.get("name"):
            return {
                "type": "function",
                "function": {"name": tc["name"]},
            }
        if tc.get("type") == "any":
            return "required"
        if tc.get("type") == "auto":
            return "auto"
    return "auto"


# ---------------------------------------------------------------------------
# Response wrappers — mimic anthropic.types.Message
# ---------------------------------------------------------------------------
class _TextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _ToolUseBlock:
    def __init__(self, id_: str, name: str, input_: dict) -> None:
        self.type = "tool_use"
        self.id = id_
        self.name = name
        self.input = input_


class _AnthropicShapedResponse:
    """Looks like anthropic.types.Message — just enough for the call sites
    in this codebase (chat.py, second_opinion.py, regulation_watcher.py,
    document_extractor.py)."""

    def __init__(self, completion) -> None:
        choice = completion.choices[0]
        msg = choice.message

        blocks: list = []
        text = getattr(msg, "content", None)
        if text:
            blocks.append(_TextBlock(text))
        tool_calls = getattr(msg, "tool_calls", None) or []
        for tc in tool_calls:
            args = tc.function.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            blocks.append(_ToolUseBlock(tc.id, tc.function.name, args))
        self.content = blocks

        fr = choice.finish_reason
        self.stop_reason = {
            "stop": "end_turn",
            "length": "max_tokens",
            "tool_calls": "tool_use",
        }.get(fr, fr or "end_turn")

        self.usage = getattr(completion, "usage", None)
        self.model = getattr(completion, "model", "")
        self.id = getattr(completion, "id", "")
        self.role = "assistant"


class _AnthropicShapedParseResponse:
    """Mimics the shape of anthropic.types.parsed_message.* — exposes
    `.parsed_output` and `.stop_reason`."""

    def __init__(self, completion) -> None:
        choice = completion.choices[0]
        msg = choice.message
        self.parsed_output = getattr(msg, "parsed", None)
        if getattr(msg, "refusal", None):
            self.stop_reason = "refusal"
        elif self.parsed_output is None:
            self.stop_reason = "no_output"
        else:
            self.stop_reason = "end_turn"
        self.usage = getattr(completion, "usage", None)


__all__ = [
    "ai_available",
    "active_backend",
    "make_client",
    "resolve_model",
]
