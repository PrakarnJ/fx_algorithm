"""Compile/runtime errors carrying source position."""


class PineError(Exception):
    def __init__(self, message: str, line: int = 0, col: int = 0):
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col

    def to_dict(self) -> dict:
        return {"line": self.line, "col": self.col, "message": self.message}


class PineCompileError(PineError):
    """Lex/parse/unsupported-feature error."""


class PineRuntimeError(PineError):
    """Error while executing a compiled script over bars."""
