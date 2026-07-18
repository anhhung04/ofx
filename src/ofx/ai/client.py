"""OpenAI-compatible LLM client for OFX AI features.

Uses the openai SDK, which works with any provider that implements the
OpenAI Chat Completions API — including OpenAI, Ollama, Groq, Together AI,
LM Studio, and Anthropic (via its openai-compatible endpoint).

Configure via OFX settings or environment variables:
  OFX_AI__API_KEY    — provider API key  (fallback: OPENAI_API_KEY)
  OFX_AI__BASE_URL   — e.g. http://localhost:11434/v1 for Ollama
  OFX_AI__MODEL      — model name (e.g. gpt-4o, llama3.2, claude-3-5-sonnet)
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass

@dataclass(slots=True)
class StreamChunk:
    """A single chunk from an LLM streaming response."""

    text: str
    kind: str = "content"

def check_ai_available() -> bool:
    """Return True if the openai SDK is installed."""
    try:
        import openai

        return True
    except ImportError:
        return False

def require_ai() -> None:
    """Raise ImportError with install instructions if openai is missing."""
    if not check_ai_available():
        raise ImportError(
            "Missing AI dependency — install it with:\n"
            "  uv add openai\n"
            "or:\n"
            "  pip install openai"
        )

def _build_client(api_key: str, base_url: str | None):
    """Create and return an openai.OpenAI client."""
    import openai

    kwargs: dict = {"api_key": api_key or "placeholder"}
    if base_url:
        kwargs["base_url"] = base_url
    return openai.OpenAI(**kwargs)

def call_llm_stream(
    messages: list[dict],
    model: str,
    api_key: str,
    temperature: float = 0.7,
    max_tokens: int = 8192,
    base_url: str | None = None,
) -> Generator[StreamChunk]:
    """Stream LLM response chunks via the OpenAI Chat Completions API.

    Yields :class:`StreamChunk` objects whose *kind* is either
    ``"thinking"`` (reasoning/chain-of-thought tokens) or ``"content"``
    (the final answer).  Models that do not emit reasoning tokens will
    only yield ``"content"`` chunks.
    """
    require_ai()

    client = _build_client(api_key, base_url)
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        thinking = getattr(delta, "reasoning_content", None)
        if thinking:
            yield StreamChunk(text=thinking, kind="thinking")

        content = delta.content
        if content:
            yield StreamChunk(text=content, kind="content")

def call_llm(
    messages: list[dict],
    model: str,
    api_key: str,
    temperature: float = 0.7,
    max_tokens: int = 8192,
    base_url: str | None = None,
) -> str:
    """Call LLM and return the full response string (non-streaming, content only)."""
    return "".join(
        c.text
        for c in call_llm_stream(
            messages=messages,
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=base_url,
        )
        if c.kind == "content"
    )
