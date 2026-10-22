"""LLM providers behind one small interface (docs/DESIGN.md §5)."""

import os
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Protocol

from tomoshibi.tools import Tool, ToolInputError, validate


class ProviderError(Exception):
    """The provider couldn't answer: no connection, bad key, outage, refusal."""

    def __init__(self, message: str, kind: str = "unavailable"):
        super().__init__(message)
        self.kind = kind  # "unavailable" | "auth" | "refusal"


class LLMProvider(Protocol):
    def stream_reply(self, stable_system: str, volatile_system: str, messages: list[dict],
                     tools: Sequence[Tool] = (), web_search: dict | None = None) -> Iterator[str]:
        """Yield the reply's text as it's generated, running any tools it calls on the way.

        `messages` is read, never modified. When the reply completes, `last_turn` holds the
        messages to add to the history: the tool calls and results (so later turns know
        how an answer was found) and the reply, without thinking blocks.
        """
        ...


MAX_TOOL_ROUNDS = 6


class AnthropicProvider:
    def __init__(self, model: str = "claude-haiku-5-5", effort: str = "low",
                 max_tokens: int = 2048, timeout: float = 20.0):
        import anthropic

        has_profile = (Path.home() / ".config" / "anthropic").is_dir()
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or has_profile):
            raise ProviderError(
                "No Anthropic API key found. Add a line ANTHROPIC_API_KEY=... to "
                "/etc/tomoshibi/secrets.env (the service) or ~/.config/tomoshibi/secrets.env "
                "(running as yourself).", "auth")
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(timeout=timeout, max_retries=1)
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.last_usage = None
        self.last_turn: list[dict] = []

    def web_search_tool(self, max_uses: int = 2, user_location: dict | None = None,
                        allowed_domains: list[str] | None = None,
                        blocked_domains: list[str] | None = None) -> dict:
        """Claude's built-in web search. On Haiku the dynamic-filtering version is accepted
        but doesn't search, so Haiku gets the basic version."""
        version = "web_search_20250305" if "haiku" in self.model else "web_search_20260209"
        tool = {"type": version, "name": "web_search", "max_uses": max_uses}
        if user_location:
            tool["user_location"] = {"type": "approximate", **user_location}
        if allowed_domains:
            tool["allowed_domains"] = allowed_domains
        elif blocked_domains:
            tool["blocked_domains"] = blocked_domains
        return tool

    @staticmethod
    def _client_tool(tool: Tool) -> dict:
        return {"name": tool.name, "description": tool.description,
                "input_schema": tool.input_schema, "strict": True, "eager_input_streaming": True}

    def stream_reply(self, stable_system: str, volatile_system: str, messages: list[dict],
                     tools: Sequence[Tool] = (), web_search: dict | None = None) -> Iterator[str]:
        a = self._anthropic
        self.last_turn = []
        convo = list(messages)
        by_name = {t.name: t for t in tools}
        kwargs = {}
        api_tools = [self._client_tool(t) for t in tools] + ([web_search] if web_search else [])
        if api_tools:
            kwargs["tools"] = api_tools
        # The stable prompt (and the tools before it) is cached; the date/time block after
        # it changes every minute. It's built once per turn, so it's identical across this
        # turn's tool rounds, as thinking blocks passed back with tool results require.
        system = [
            {"type": "text", "text": stable_system, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": volatile_system},
        ]
        spoke = False  # separate text blocks (e.g. "Let me check." and the answer) need a space
        for _ in range(MAX_TOOL_ROUNDS):
            try:
                with self._client.messages.stream(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system,
                    messages=convo,
                    # Spoken chat: keep thinking light so speech starts quickly.
                    output_config={"effort": self.effort},
                    **kwargs,
                ) as stream:
                    for event in stream:
                        if event.type == "content_block_start" and event.content_block.type == "text":
                            if spoke:
                                yield " "
                        elif event.type == "content_block_delta" and event.delta.type == "text_delta":
                            spoke = True
                            yield event.delta.text
                    final = stream.get_final_message()
            except ValueError as e:  # a tool input the SDK couldn't parse at all
                raise ProviderError(f"unreadable tool input: {e}") from e
            except a.AuthenticationError as e:
                raise ProviderError(str(e), "auth") from e
            except a.PermissionDeniedError as e:
                raise ProviderError(str(e), "auth") from e
            except a.RateLimitError as e:
                raise ProviderError(str(e)) from e
            except a.APIStatusError as e:
                raise ProviderError(f"{e.status_code}: {e.message}") from e
            except a.APIConnectionError as e:
                raise ProviderError(str(e)) from e
            self.last_usage = final.usage
            if final.stop_reason == "refusal":
                raise ProviderError("refused", "refusal")
            if final.stop_reason == "pause_turn":  # a long server-side search: let it carry on
                convo.append({"role": "assistant", "content": final.content})
                continue
            if final.stop_reason != "tool_use":
                convo.append({"role": "assistant", "content": final.content})
                self.last_turn = [_without_thinking(m) for m in convo[len(messages):]]
                return
            convo.append({"role": "assistant", "content": final.content})
            convo.append({"role": "user", "content": [
                self._run_tool(by_name, block) for block in final.content if block.type == "tool_use"
            ]})
        raise ProviderError("too many tool calls in one answer")

    @staticmethod
    def _run_tool(by_name: dict[str, Tool], block) -> dict:
        tool = by_name.get(block.name)
        if tool is None:
            return {"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                    "content": f"Unknown tool {block.name}."}
        try:
            output = tool.run(validate(tool.input_schema, block.input))
        except ToolInputError as e:
            return {"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                    "content": f"INVALID_INPUT: {e}"}
        return {"type": "tool_result", "tool_use_id": block.id, "content": output}


def _without_thinking(message: dict) -> dict:
    """Finished turns are kept without their thinking blocks. A thinking block is only valid
    while everything before it is unchanged, and the date/time part of the system prompt
    changes between turns; without the blocks there is nothing to invalidate."""
    content = message["content"]
    if message["role"] != "assistant" or isinstance(content, str):
        return message
    return {"role": "assistant",
            "content": [b for b in content if getattr(b, "type", None) not in ("thinking", "redacted_thinking")]}


def from_config(config: dict) -> LLMProvider:
    primary = (config.get("llm") or {}).get("primary") or {}
    provider = primary.get("provider", "anthropic")
    if provider != "anthropic":
        raise ProviderError(f"provider {provider!r} is not built yet", "unavailable")
    return AnthropicProvider(model=primary.get("model", "claude-haiku-5-5"),
                             effort=primary.get("effort", "low"))
