"""Chat history management with token tracking and auto-compaction."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChatHistory:
    """Wraps LLM message list with token estimation and auto-compaction.

    Token estimation uses the rough heuristic of 1 token per 4 characters,
    matching secator's approach — accurate enough to trigger compaction before
    hitting hard API limits.
    """

    messages: list[dict] = field(default_factory=list)
    _system: str = field(default="", init=False, repr=False)

    def set_system(self, content: str) -> None:
        """Set or replace the system prompt."""
        self._system = content
        self.messages = [m for m in self.messages if m["role"] != "system"]
        if content:
            self.messages.insert(0, {"role": "system", "content": content})

    def add_user(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def est_tokens(self) -> int:
        """Rough token estimate: ~4 chars per token."""
        return sum(len(m.get("content", "")) for m in self.messages) // 4

    def maybe_compact(
        self,
        model: str,
        api_key: str,
        threshold: int = 30000,
        base_url: str | None = None,
    ) -> bool:
        """Summarize and compact history if token count exceeds threshold.

        Keeps the system prompt intact and replaces the conversation body with
        an LLM-generated summary.  Returns True if compaction happened.
        """
        if self.est_tokens() < threshold:
            return False

        from ofx.ai.client import call_llm

        summary_prompt = (
            "Summarize the conversation so far. Preserve all key findings, "
            "commands run, outputs received, and decisions made. Be concise."
        )
        summary_msgs = list(self.messages) + [
            {"role": "user", "content": summary_prompt}
        ]
        summary = call_llm(
            summary_msgs,
            model=model,
            api_key=api_key,
            base_url=base_url,
            max_tokens=2048,
        )

        self.messages = []
        if self._system:
            self.messages.append({"role": "system", "content": self._system})
        self.messages.append(
            {"role": "assistant", "content": f"[Conversation summary]\n{summary}"}
        )
        return True

    def to_list(self) -> list[dict]:
        return list(self.messages)
