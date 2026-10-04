from __future__ import annotations

from typing import Protocol

from app.services.knowledge.errors import TokenizerUnavailableError


class TokenEncoding(Protocol):
    def encode(self, text: str) -> list[int]: ...

    def decode(self, tokens: list[int]) -> str: ...


class KnowledgeTokenizer:
    def __init__(self, model: str) -> None:
        try:
            import tiktoken
        except ImportError as exc:
            raise TokenizerUnavailableError() from exc
        try:
            self._encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            try:
                self._encoding = tiktoken.get_encoding("o200k_base")
            except Exception as exc:
                raise TokenizerUnavailableError() from exc
        except Exception as exc:
            raise TokenizerUnavailableError() from exc

    def encode(self, text: str) -> list[int]:
        try:
            return list(self._encoding.encode(text))
        except Exception as exc:
            raise TokenizerUnavailableError() from exc

    def decode(self, tokens: list[int]) -> str:
        try:
            return str(self._encoding.decode(tokens))
        except Exception as exc:
            raise TokenizerUnavailableError() from exc

    def count(self, text: str) -> int:
        return len(self.encode(text))
