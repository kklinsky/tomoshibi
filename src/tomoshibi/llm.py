"""LLM providers behind one small interface (docs/DESIGN.md §5)."""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol


class ProviderError(Exception):
    """The provider couldn't answer: no connection, bad key, outage, refusal."""

    def __init__(self, message: str, kind: str = "unavailable"):
        super().__init__(message)
        self.kind = kind  # "unavailable" | "auth" | "refusal"


class LLMProvider(Protocol):
    def stream_reply(self, stable_system: str, volatile_system: str,
                     messages: list[dict]) -> Iterator[str]:
        """Yield the reply's text as it's generated."""
        ...


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

    def stream_reply(self, stable_system: str, volatile_system: str,
                     messages: list[dict]) -> Iterator[str]:
        a = self._anthropic
        try:
            with self._client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                # The stable prompt is cached; the date/time block after it changes every minute.
                system=[
                    {"type": "text", "text": stable_system, "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": volatile_system},
                ],
                messages=messages,
                # Spoken chat: keep thinking light so speech starts quickly.
                output_config={"effort": self.effort},
            ) as stream:
                yield from stream.text_stream
                final = stream.get_final_message()
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
        if final.stop_reason == "refusal":
            raise ProviderError("refused", "refusal")
        self.last_usage = final.usage


def from_config(config: dict) -> LLMProvider:
    primary = (config.get("llm") or {}).get("primary") or {}
    provider = primary.get("provider", "anthropic")
    if provider != "anthropic":
        raise ProviderError(f"provider {provider!r} is not built yet", "unavailable")
    return AnthropicProvider(model=primary.get("model", "claude-haiku-5-5"),
                             effort=primary.get("effort", "low"))
