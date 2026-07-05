"""AST node definitions. Every node carries line/col for error reporting.

Nodes that need per-callsite runtime state (ta.* incremental state, historical
buffers) get a unique `uid` assigned by the parser.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Node:
    line: int = 0
    col: int = 0


@dataclass
class Num(Node):
    value: float = 0.0


@dataclass
class Str(Node):
    value: str = ""


@dataclass
class Bool(Node):
    value: bool = False


@dataclass
class Na(Node):
    pass


@dataclass
class ColorLit(Node):
    value: str = "#000000"  # normalized "#RRGGBB" or "#RRGGBBAA"


@dataclass
class Ident(Node):
    name: str = ""


@dataclass
class Call(Node):
    func: str = ""
    args: list = field(default_factory=list)
    kwargs: dict = field(default_factory=dict)
    uid: int = -1


@dataclass
class HistRef(Node):
    """expr[n] — historical series access."""
    base: Any = None
    index: Any = None
    uid: int = -1


@dataclass
class BinOp(Node):
    op: str = ""
    left: Any = None
    right: Any = None


@dataclass
class UnaryOp(Node):
    op: str = ""
    operand: Any = None


@dataclass
class Ternary(Node):
    cond: Any = None
    then: Any = None
    other: Any = None


@dataclass
class Assign(Node):
    """x = expr | var x = expr | x := expr"""
    name: str = ""
    expr: Any = None
    mode: str = "declare"  # "declare" | "var" | "reassign"


@dataclass
class TupleAssign(Node):
    names: list = field(default_factory=list)
    call: Any = None


@dataclass
class If(Node):
    cond: Any = None
    body: list = field(default_factory=list)
    orelse: list = field(default_factory=list)


@dataclass
class For(Node):
    """for VAR = start to end (step ±1 toward end, TV semantics)"""
    var: str = ""
    start: Any = None
    end: Any = None
    body: list = field(default_factory=list)


@dataclass
class FuncDef(Node):
    """name(params) => expr | indented block (last statement is the return value)"""
    name: str = ""
    params: list = field(default_factory=list)
    body: list = field(default_factory=list)


@dataclass
class ListLit(Node):
    items: list = field(default_factory=list)


@dataclass
class ExprStmt(Node):
    expr: Any = None


@dataclass
class Program(Node):
    version: int = 5
    script_type: str = "indicator"   # "indicator" | "strategy"
    title: str = ""
    overlay: bool = True
    # strategy() declaration args (already literal-evaluated)
    settings: dict = field(default_factory=dict)
    functions: dict = field(default_factory=dict)   # name → FuncDef
    body: list = field(default_factory=list)
