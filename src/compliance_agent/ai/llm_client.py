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
        model="claude-opus-4-8",
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
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


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

    Anthropic path: passes through unchanged (e.g. claude-opus-4-8).
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
# Per-run token-usage logging — so real spend is visible in the server logs.
# ---------------------------------------------------------------------------
# Anthropic list price, USD per 1M tokens (input, output). OpenRouter is
# pass-through, so these are a close proxy for the OpenRouter path too. Cache
# reads bill ~0.1x input and cache writes ~1.25x input (5-minute TTL).
_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def _price_for(model: str) -> tuple[Optional[float], Optional[float]]:
    """(input, output) USD per 1M tokens for `model`, or (None, None) if we
    don't have a price for it. Strips an OpenRouter-style 'anthropic/' prefix
    and any ':variant' suffix before matching."""
    key = model.split("/")[-1].split(":")[0]
    return _PRICING_PER_MTOK.get(key, (None, None))


def log_usage(response: Any, *, model: str, label: str) -> None:
    """Log token usage (plus a best-effort USD estimate) for one AI call.

    Token counts come straight from the response and are exact. The dollar
    figure is an ESTIMATE from Anthropic list prices for the model actually
    billed (`resolve_model`, so the OpenRouter model is used on that path, not
    the requested one); it's omitted when we have no price for that model.
    No-op when the backend didn't return a usage object."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return

    # Two shapes: Anthropic (input_tokens/output_tokens/cache_*) where
    # input_tokens is the uncached remainder, or OpenAI-via-OpenRouter
    # (prompt_tokens/completion_tokens) where prompt_tokens is the full input
    # and any cached tokens are a subset reported in prompt_tokens_details.
    if hasattr(usage, "input_tokens"):
        uncached_in = int(getattr(usage, "input_tokens", 0) or 0)
        out = int(getattr(usage, "output_tokens", 0) or 0)
        cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        cache_write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    else:
        total_in = int(getattr(usage, "prompt_tokens", 0) or 0)
        out = int(getattr(usage, "completion_tokens", 0) or 0)
        details = getattr(usage, "prompt_tokens_details", None)
        cache_read = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
        cache_write = 0
        uncached_in = total_in - cache_read

    billed_model = resolve_model(model)
    in_rate, out_rate = _price_for(billed_model)
    if in_rate is not None and out_rate is not None:
        cost = (
            uncached_in * in_rate
            + cache_read * in_rate * 0.10
            + cache_write * in_rate * 1.25
            + out * out_rate
        ) / 1_000_000
        cost_str = f"~${cost:.4f}"
    else:
        cost_str = "n/a"

    logger.info(
        "AI usage [%s] backend=%s model=%s in=%d out=%d cache_read=%d "
        "cache_write=%d est_cost=%s",
        label,
        active_backend(),
        billed_model,
        uncached_in + cache_read + cache_write,
        out,
        cache_read,
        cache_write,
        cost_str,
    )


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
        model_id = resolve_model(model)
        # OpenAI-native structured output (json_schema). Works for OpenAI models
        # on OpenRouter, but many providers — incl. Anthropic models via
        # OpenRouter — don't ENFORCE the schema, so the reply comes back as
        # prose/markdown and the SDK's strict json.loads raises. Try it; on any
        # failure, fall back to asking for plain JSON and validating it ourselves.
        if output_format is not None:
            try:
                completion = self._openai.beta.chat.completions.parse(
                    model=model_id,
                    messages=oa_messages,
                    max_tokens=max_tokens,
                    response_format=output_format,
                )
                shaped = _AnthropicShapedParseResponse(completion)
                if shaped.parsed_output is not None:
                    return shaped
            except Exception:
                pass
        return self._parse_json_fallback(model_id, oa_messages, max_tokens, output_format)

    def _parse_json_fallback(self, model_id, oa_messages, max_tokens, output_format):
        """Provider-agnostic structured output: instruct the model to emit a raw
        JSON object matching the schema, then extract + validate it. Used when
        json_schema isn't enforced (e.g. Anthropic models via OpenRouter)."""
        msgs = list(oa_messages)
        if output_format is not None:
            schema = json.dumps(output_format.model_json_schema())
            instruction = (
                "\n\nReturn ONLY a single JSON object that conforms to this JSON "
                "Schema. No prose, no explanation, no markdown code fences:\n" + schema
            )
            if (
                msgs
                and msgs[-1].get("role") == "user"
                and isinstance(msgs[-1].get("content"), str)
            ):
                msgs[-1] = {**msgs[-1], "content": msgs[-1]["content"] + instruction}
            else:
                msgs.append({"role": "user", "content": instruction.strip()})
        completion = self._openai.chat.completions.create(
            model=model_id,
            messages=msgs,
            max_tokens=max_tokens,
        )
        return _ManualParseResponse(completion, output_format)


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


def _extract_json(text: str) -> str:
    """Pull the JSON object/array out of a model reply that may be wrapped in
    markdown fences or padded with prose (the non-strict providers do this)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[A-Za-z0-9]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    starts = [i for i in (t.find("{"), t.find("[")) if i != -1]
    if not starts:
        return t
    start = min(starts)
    end = max(t.rfind("}"), t.rfind("]"))
    return t[start : end + 1] if end > start else t


class _ManualParseResponse:
    """Like _AnthropicShapedParseResponse, but we parse the model's text reply as
    JSON ourselves and validate it against the Pydantic output_format — for
    providers that don't enforce json_schema structured output."""

    def __init__(self, completion, output_format) -> None:
        choice = completion.choices[0]
        raw = getattr(choice.message, "content", None) or ""
        self.parsed_output = None
        self.stop_reason = "no_output"
        if output_format is not None and raw.strip():
            try:
                self.parsed_output = output_format.model_validate_json(_extract_json(raw))
                self.stop_reason = "end_turn"
            except Exception:
                self.stop_reason = "no_output"
        self.usage = getattr(completion, "usage", None)


__all__ = [
    "ai_available",
    "active_backend",
    "make_client",
    "resolve_model",
    "log_usage",
]
