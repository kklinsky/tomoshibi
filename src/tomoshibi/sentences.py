"""Splits streaming text into speakable pieces, so speech can start before the reply ends."""

import re

_END = re.compile(r"""[.!?]+["')\]]*\s+|\n+""")
FIRST_CHUNK_MAX = 80  # a long first sentence is cut at a comma so the first audio comes sooner


class SentenceSplitter:
    def __init__(self) -> None:
        self._buffer = ""
        self._first = True

    def feed(self, text: str) -> list[str]:
        """Add streamed text; return any pieces now complete."""
        self._buffer += text
        out = []
        while True:
            match = _END.search(self._buffer)
            if self._first and (not match or match.end() > FIRST_CHUNK_MAX):
                comma = self._buffer.find(", ", 20)
                if 0 < comma < FIRST_CHUNK_MAX:
                    out.append(self._buffer[: comma + 1].strip())
                    self._buffer = self._buffer[comma + 2:]
                    self._first = False
                    continue
            if not match:
                break
            piece = self._buffer[: match.end()].strip()
            self._buffer = self._buffer[match.end():]
            if piece:
                out.append(piece)
                self._first = False
        return out

    def flush(self) -> list[str]:
        piece, self._buffer = self._buffer.strip(), ""
        return [piece] if piece else []
