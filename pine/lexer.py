"""Tokenizer for the Pine subset.

Emits a flat token list. Newlines are significant (statement separators) and
carry the indentation of the *next* line so the parser can build if/else
blocks. Newlines are suppressed inside brackets and after trailing operators
(line continuation).
"""
from __future__ import annotations

from dataclasses import dataclass

from pine.errors import PineCompileError

# Token kinds
NUMBER, STRING, IDENT, OP, NEWLINE, EOF, COLOR = (
    "NUMBER", "STRING", "IDENT", "OP", "NEWLINE", "EOF", "COLOR")

KEYWORDS = {"var", "if", "else", "and", "or", "not", "true", "false", "na"}

# Multi-char operators first (longest match wins)
_OPS = [":=", "==", "!=", "<=", ">=", "=>", "+=", "-=", "+", "-", "*", "/", "%",
        "<", ">", "=", "(", ")", "[", "]", ",", "?", ":"]

_CONTINUATION_OPS = {":=", "==", "!=", "<=", ">=", "+", "-", "*", "/", "%",
                     "<", ">", "=", ",", "?", ":", "(", "[", "and", "or", "not"}


@dataclass
class Token:
    kind: str
    value: str
    line: int
    col: int

    def __repr__(self):  # pragma: no cover — debug aid
        return f"{self.kind}({self.value!r})@{self.line}:{self.col}"


def tokenize(src: str) -> tuple[list[Token], int]:
    """Return (tokens, version). version defaults to 5 when no directive."""
    tokens: list[Token] = []
    version = 5
    depth = 0  # bracket nesting — newlines inside are ignored

    lines = src.split("\n")
    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip()
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        # Blank lines and pure comments
        if not stripped or stripped.startswith("//"):
            if stripped.startswith("//@version"):
                try:
                    version = int(stripped.split("=", 1)[1].strip())
                except (IndexError, ValueError):
                    raise PineCompileError("malformed //@version directive", lineno, 1)
                if version < 4:
                    raise PineCompileError(
                        f"//@version={version} is not supported — this engine implements "
                        "Pine v4/v5/v6 syntax (ta.* namespace, var/varip, arrays). "
                        "Pre-v4 scripts use different built-in names and won't parse.",
                        lineno, 1)
                if version > 6:
                    raise PineCompileError(
                        f"//@version={version} is newer than this engine supports "
                        "(implements Pine v4–v6 syntax)", lineno, 1)
            continue

        # Continuation line: bracket depth open, or previous token invites more
        is_continuation = depth > 0 or (
            tokens and tokens[-1].kind != NEWLINE
            and tokens[-1].value in _CONTINUATION_OPS
        )
        if tokens and not is_continuation:
            tokens.append(Token(NEWLINE, str(indent), lineno, 1))
        elif not tokens:
            # First code line establishes base indent via a leading NEWLINE
            tokens.append(Token(NEWLINE, str(indent), lineno, 1))

        i = 0
        n = len(line)
        while i < n:
            c = line[i]
            col = i + 1

            if c in " \t":
                i += 1
                continue
            if c == "/" and i + 1 < n and line[i + 1] == "/":
                break  # comment to end of line

            # String literal
            if c in "'\"":
                quote = c
                j = i + 1
                buf = []
                while j < n and line[j] != quote:
                    if line[j] == "\\" and j + 1 < n:
                        buf.append(line[j + 1])
                        j += 2
                    else:
                        buf.append(line[j])
                        j += 1
                if j >= n:
                    raise PineCompileError("unterminated string literal", lineno, col)
                tokens.append(Token(STRING, "".join(buf), lineno, col))
                i = j + 1
                continue

            # Color literal #RRGGBB or #RRGGBBAA
            if c == "#":
                j = i + 1
                while j < n and line[j] in "0123456789abcdefABCDEF":
                    j += 1
                hexlen = j - i - 1
                if hexlen not in (6, 8):
                    raise PineCompileError("malformed color literal", lineno, col)
                tokens.append(Token(COLOR, line[i:j], lineno, col))
                i = j
                continue

            # Number
            if c.isdigit() or (c == "." and i + 1 < n and line[i + 1].isdigit()):
                j = i
                seen_dot = False
                while j < n and (line[j].isdigit() or (line[j] == "." and not seen_dot)):
                    if line[j] == ".":
                        # `1.` followed by identifier would be weird; Pine numbers are simple
                        seen_dot = True
                    j += 1
                # scientific notation
                if j < n and line[j] in "eE":
                    k = j + 1
                    if k < n and line[k] in "+-":
                        k += 1
                    if k < n and line[k].isdigit():
                        while k < n and line[k].isdigit():
                            k += 1
                        j = k
                tokens.append(Token(NUMBER, line[i:j], lineno, col))
                i = j
                continue

            # Identifier — dotted namespaces lex as one token (ta.ema, strategy.long)
            if c.isalpha() or c == "_":
                j = i
                while j < n and (line[j].isalnum() or line[j] in "_."):
                    j += 1
                # Trailing dot is not part of the name
                while line[j - 1] == ".":
                    j -= 1
                tokens.append(Token(IDENT, line[i:j], lineno, col))
                i = j
                continue

            # Operators
            for op in _OPS:
                if line.startswith(op, i):
                    tokens.append(Token(OP, op, lineno, col))
                    if op in "([":
                        depth += 1
                    elif op in ")]":
                        depth = max(0, depth - 1)
                    i += len(op)
                    break
            else:
                raise PineCompileError(f"unexpected character {c!r}", lineno, col)

    tokens.append(Token(NEWLINE, "0", len(lines) + 1, 1))
    tokens.append(Token(EOF, "", len(lines) + 1, 1))
    return tokens, version
