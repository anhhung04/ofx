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


def check_ai_available() -> bool:
    """Return True if the openai SDK is installed."""
    try:
        import openai  # noqa: F401

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
) -> Generator[str, None, None]:
    """Stream LLM response text chunks via the OpenAI Chat Completions API.

    System messages are included directly in `messages` as
    {"role": "system", "content": "..."} — no special handling needed.
    """
    require_ai()

    client = _build_client(api_key, base_url)
    stream = client.chat.completions.create(
        model=model,
        messages=messages,  # type: ignore[arg-type]
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            yield content


def call_llm(
    messages: list[dict],
    model: str,
    api_key: str,
    temperature: float = 0.7,
    max_tokens: int = 8192,
    base_url: str | None = None,
) -> str:
    """Call LLM and return the full response string (non-streaming)."""
    return "".join(
        call_llm_stream(
            messages=messages,
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=base_url,
        )
    )
