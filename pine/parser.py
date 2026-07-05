"""Recursive-descent parser for the Pine subset.

Grammar (statements are newline-separated; if/else bodies are indented blocks):

  program   := NEWLINE? decl? stmt*
  stmt      := assign | tuple_assign | if_stmt | expr_stmt
  assign    := ["var"] IDENT ("=" | ":=") expr
  tuple     := "[" IDENT ("," IDENT)* "]" "=" call
  if_stmt   := "if" expr block ("else" (if_stmt | block))?
  expr      := ternary
  ternary   := or_ ("?" expr ":" expr)?
  or_       := and_ ("or" and_)*
  and_      := not_ ("and" not_)*
  not_      := "not" not_ | cmp
  cmp       := add (("=="|"!="|"<"|">"|"<="|">=") add)*
  add       := mul (("+"|"-") mul)*
  mul       := unary (("*"|"/"|"%") unary)*
  unary     := ("-"|"+") unary | postfix
  postfix   := primary ("[" expr "]")*
  primary   := NUMBER | STRING | COLOR | "true" | "false" | "na"
             | IDENT "(" args ")" | IDENT | "(" expr ")"
"""
from __future__ import annotations

from pine import ast_nodes as A
from pine.errors import PineCompileError
from pine.lexer import Token, tokenize, NUMBER, STRING, IDENT, OP, NEWLINE, EOF, COLOR

# Features recognized but rejected loudly (better message than "unexpected token")
_UNSUPPORTED_CALLS = {
    "request.security": "request.security / higher-timeframe data is not supported (single-timeframe scripts only)",
    "matrix.new": "matrices are not supported",
    "line.new": "drawing objects (line.*) are not supported",
    "label.new": "drawing objects (label.*) are not supported",
    "box.new": "drawing objects (box.*) are not supported",
    "table.new": "tables are not supported",
}

_UNSUPPORTED_KEYWORDS = {"while", "switch", "method", "type", "import", "export"}

# Type names that may precede a variable name in a declaration
_TYPE_NAMES = {"float", "int", "bool", "string", "color", "label", "line", "box", "array", "matrix"}


class Parser:
    def __init__(self, src: str):
        self.tokens, self.version = tokenize(src)
        self.pos = 0
        self._uid = 0

    # ── token helpers ────────────────────────────────────────────────────────
    def peek(self, offset: int = 0) -> Token:
        return self.tokens[min(self.pos + offset, len(self.tokens) - 1)]

    def next(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.kind != EOF:
            self.pos += 1
        return tok

    def expect(self, kind: str, value: str | None = None) -> Token:
        tok = self.peek()
        if tok.kind != kind or (value is not None and tok.value != value):
            want = value or kind
            raise PineCompileError(f"expected {want!r}, got {tok.value!r}", tok.line, tok.col)
        return self.next()

    def at_op(self, value: str) -> bool:
        tok = self.peek()
        return tok.kind == OP and tok.value == value

    def skip_newlines(self) -> None:
        while self.peek().kind == NEWLINE:
            self.next()

    def new_uid(self) -> int:
        self._uid += 1
        return self._uid

    # ── program ──────────────────────────────────────────────────────────────
    def parse(self) -> A.Program:
        prog = A.Program(version=self.version)
        got_decl = False

        while self.peek().kind != EOF:
            if self.peek().kind == NEWLINE:
                self.next()
                continue
            indent = self._current_indent()
            if indent != 0:
                tok = self.peek()
                raise PineCompileError("unexpected indentation at top level", tok.line, tok.col)
            stmt = self.parse_stmt(indent=0)
            if stmt is None:
                continue
            # First indicator()/strategy() call is the declaration
            if (not got_decl and isinstance(stmt, A.ExprStmt)
                    and isinstance(stmt.expr, A.Call)
                    and stmt.expr.func in ("indicator", "strategy", "study")):
                self._apply_declaration(prog, stmt.expr)
                got_decl = True
                continue
            # User function definitions live in the program's function table
            if isinstance(stmt, A.FuncDef):
                prog.functions[stmt.name] = stmt
                continue
            prog.body.append(stmt)

        if not got_decl:
            raise PineCompileError(
                "script must declare indicator(...) or strategy(...)", 1, 1)
        return prog

    def _apply_declaration(self, prog: A.Program, call: A.Call) -> None:
        prog.script_type = "strategy" if call.func == "strategy" else "indicator"
        lit = {}
        for i, arg in enumerate(call.args):
            key = "title" if i == 0 else f"_arg{i}"
            lit[key] = self._literal(arg)
        for k, v in call.kwargs.items():
            lit[k] = self._literal(v)
        prog.title = str(lit.get("title", "Untitled script"))
        prog.overlay = bool(lit.get("overlay", prog.script_type == "strategy"))
        pyramiding = lit.get("pyramiding", 1)
        if pyramiding not in (0, 1):
            raise PineCompileError(
                "pyramiding > 1 is not supported (single position only)",
                call.line, call.col)
        prog.settings = {
            k: v for k, v in lit.items()
            if k in ("initial_capital", "default_qty_type", "default_qty_value",
                     "commission_type", "commission_value", "process_orders_on_close")
        }

    def _literal(self, node) -> object:
        """Evaluate a declaration argument — literals only."""
        if isinstance(node, A.Num):
            return node.value
        if isinstance(node, A.Str):
            return node.value
        if isinstance(node, A.Bool):
            return node.value
        if isinstance(node, A.Ident):
            # strategy.percent_of_equity etc. → last namespace component
            return node.name.split(".")[-1]
        if isinstance(node, A.UnaryOp) and isinstance(node.operand, A.Num):
            return -node.operand.value if node.op == "-" else node.operand.value
        raise PineCompileError(
            "declaration arguments must be literals", node.line, node.col)

    # ── statements ────────────────────────────────────────────────────────────
    def _current_indent(self) -> int:
        """Indent of the statement about to be parsed (from preceding NEWLINE)."""
        i = self.pos - 1
        while i >= 0 and self.tokens[i].kind != NEWLINE:
            i -= 1
        return int(self.tokens[i].value) if i >= 0 else 0

    def parse_stmt(self, indent: int):
        tok = self.peek()

        if tok.kind == IDENT and tok.value in _UNSUPPORTED_KEYWORDS:
            raise PineCompileError(
                f"{tok.value!r} is not supported in this Pine subset", tok.line, tok.col)

        if tok.kind == IDENT and tok.value == "if":
            return self.parse_if(indent)

        if tok.kind == IDENT and tok.value == "for":
            return self.parse_for(indent)

        # Tuple destructuring: [a, b, c] = call(...)  (vs a bare list literal)
        if self.at_op("[") and self._is_tuple_assign():
            return self.parse_tuple_assign()

        # var [type] x = expr — optional type annotation (float, array<float>, …)
        if tok.kind == IDENT and tok.value == "var":
            self.next()
            self._skip_type_annotation()
            name_tok = self.expect(IDENT)
            self.expect(OP, "=")
            expr = self.parse_expr()
            self._end_stmt()
            return A.Assign(tok.line, tok.col, name=name_tok.value, expr=expr, mode="var")

        # name(params) => … — user function definition
        if tok.kind == IDENT and self.peek(1).kind == OP and self.peek(1).value == "(" \
                and self._is_funcdef():
            return self.parse_funcdef(indent)

        # typed declaration without var: float x = expr
        if (tok.kind == IDENT and tok.value in _TYPE_NAMES
                and self.peek(1).kind == IDENT
                and self.peek(2).kind == OP and self.peek(2).value == "="):
            self.next()  # drop the type
            tok = self.peek()

        # x = expr | x := expr | x += expr | x -= expr
        if tok.kind == IDENT and self.peek(1).kind == OP \
                and self.peek(1).value in ("=", ":=", "+=", "-="):
            self.next()
            op = self.next()
            expr = self.parse_expr()
            self._end_stmt()
            if op.value in ("+=", "-="):
                # desugar: x += e  →  x := x + e
                expr = A.BinOp(op.line, op.col, op=op.value[0],
                               left=A.Ident(tok.line, tok.col, name=tok.value),
                               right=expr)
                return A.Assign(tok.line, tok.col, name=tok.value, expr=expr, mode="reassign")
            mode = "reassign" if op.value == ":=" else "declare"
            return A.Assign(tok.line, tok.col, name=tok.value, expr=expr, mode=mode)

        # Bare expression (plot(...), strategy.entry(...))
        expr = self.parse_expr()
        self._end_stmt()
        return A.ExprStmt(tok.line, tok.col, expr=expr)

    def _skip_type_annotation(self) -> None:
        """Consume an optional type before a declared name: `float`, `array<float>`…"""
        tok = self.peek()
        if tok.kind != IDENT or tok.value not in _TYPE_NAMES:
            return
        # It's only a type if another identifier (the actual name) follows
        nxt = self.peek(1)
        if nxt.kind == OP and nxt.value == "<":
            self.next()  # type name
            self.next()  # '<'
            self.expect(IDENT)
            self.expect(OP, ">")
        elif nxt.kind == IDENT:
            self.next()

    def _is_tuple_assign(self) -> bool:
        """Lookahead: `[ IDENT (, IDENT)* ] =` — else it's a list literal."""
        i = self.pos + 1
        toks = self.tokens
        while i < len(toks):
            t = toks[i]
            if t.kind == IDENT or (t.kind == OP and t.value == ","):
                i += 1
                continue
            if t.kind == OP and t.value == "]":
                nxt = toks[i + 1] if i + 1 < len(toks) else None
                return nxt is not None and nxt.kind == OP and nxt.value == "="
            return False
        return False

    def _is_funcdef(self) -> bool:
        """Lookahead from `IDENT (`: does the matching `)` precede `=>`?"""
        i = self.pos + 1  # at '('
        depth = 0
        toks = self.tokens
        while i < len(toks):
            t = toks[i]
            if t.kind == OP and t.value in ("(", "["):
                depth += 1
            elif t.kind == OP and t.value in (")", "]"):
                depth -= 1
                if depth == 0:
                    nxt = toks[i + 1] if i + 1 < len(toks) else None
                    return nxt is not None and nxt.kind == OP and nxt.value == "=>"
            elif t.kind in (NEWLINE, EOF):
                return False
            i += 1
        return False

    def parse_funcdef(self, indent: int) -> A.FuncDef:
        name_tok = self.expect(IDENT)
        if indent != 0:
            raise PineCompileError("function definitions must be at top level",
                                   name_tok.line, name_tok.col)
        self.expect(OP, "(")
        params: list = []
        if not self.at_op(")"):
            params.append(self.expect(IDENT).value)
            while self.at_op(","):
                self.next()
                params.append(self.expect(IDENT).value)
        self.expect(OP, ")")
        self.expect(OP, "=>")
        if self.peek().kind == NEWLINE:
            body = self.parse_block(indent)
        else:
            expr = self.parse_expr()
            self._end_stmt()
            body = [A.ExprStmt(name_tok.line, name_tok.col, expr=expr)]
        return A.FuncDef(name_tok.line, name_tok.col,
                         name=name_tok.value, params=params, body=body)

    def parse_for(self, indent: int) -> A.For:
        for_tok = self.expect(IDENT, "for")
        var_tok = self.expect(IDENT)
        self.expect(OP, "=")
        start = self.parse_expr()
        to_tok = self.expect(IDENT)
        if to_tok.value != "to":
            raise PineCompileError("expected 'to' in for loop", to_tok.line, to_tok.col)
        end = self.parse_expr()
        if self.peek().kind == IDENT and self.peek().value == "by":
            raise PineCompileError("'by' step in for loops is not supported",
                                   self.peek().line, self.peek().col)
        body = self.parse_block(indent)
        return A.For(for_tok.line, for_tok.col, var=var_tok.value,
                     start=start, end=end, body=body)

    def _end_stmt(self) -> None:
        tok = self.peek()
        if tok.kind not in (NEWLINE, EOF):
            raise PineCompileError(f"unexpected {tok.value!r} after statement",
                                   tok.line, tok.col)

    def parse_tuple_assign(self) -> A.TupleAssign:
        start = self.expect(OP, "[")
        names = [self.expect(IDENT).value]
        while self.at_op(","):
            self.next()
            names.append(self.expect(IDENT).value)
        self.expect(OP, "]")
        self.expect(OP, "=")
        expr = self.parse_expr()
        if not isinstance(expr, A.Call):
            raise PineCompileError("tuple assignment requires a function call",
                                   start.line, start.col)
        self._end_stmt()
        return A.TupleAssign(start.line, start.col, names=names, call=expr)

    def parse_if(self, indent: int) -> A.If:
        if_tok = self.expect(IDENT, "if")
        cond = self.parse_expr()
        body = self.parse_block(indent)
        orelse: list = []
        # `else` must sit at the same indent as the `if`
        save = self.pos
        self.skip_newlines()
        tok = self.peek()
        if tok.kind == IDENT and tok.value == "else" and self._current_indent() == indent:
            self.next()
            if self.peek().kind == IDENT and self.peek().value == "if":
                orelse = [self.parse_if(indent)]
            else:
                orelse = self.parse_block(indent)
        else:
            self.pos = save
        return A.If(if_tok.line, if_tok.col, cond=cond, body=body, orelse=orelse)

    def parse_block(self, parent_indent: int) -> list:
        """Indented statements following an if/else header."""
        stmts: list = []
        while True:
            save = self.pos
            self.skip_newlines()
            if self.peek().kind == EOF:
                break
            indent = self._current_indent()
            if indent <= parent_indent:
                self.pos = save
                break
            stmts.append(self.parse_stmt(indent))
        if not stmts:
            tok = self.peek()
            raise PineCompileError("expected an indented block", tok.line, tok.col)
        return stmts

    # ── expressions ───────────────────────────────────────────────────────────
    def parse_expr(self):
        return self.parse_ternary()

    def parse_ternary(self):
        cond = self.parse_or()
        if self.at_op("?"):
            q = self.next()
            then = self.parse_expr()
            self.expect(OP, ":")
            other = self.parse_expr()
            return A.Ternary(q.line, q.col, cond=cond, then=then, other=other)
        return cond

    def parse_or(self):
        left = self.parse_and()
        while self.peek().kind == IDENT and self.peek().value == "or":
            tok = self.next()
            right = self.parse_and()
            left = A.BinOp(tok.line, tok.col, op="or", left=left, right=right)
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.peek().kind == IDENT and self.peek().value == "and":
            tok = self.next()
            right = self.parse_not()
            left = A.BinOp(tok.line, tok.col, op="and", left=left, right=right)
        return left

    def parse_not(self):
        if self.peek().kind == IDENT and self.peek().value == "not":
            tok = self.next()
            return A.UnaryOp(tok.line, tok.col, op="not", operand=self.parse_not())
        return self.parse_cmp()

    def parse_cmp(self):
        left = self.parse_add()
        while self.peek().kind == OP and self.peek().value in ("==", "!=", "<", ">", "<=", ">="):
            tok = self.next()
            right = self.parse_add()
            left = A.BinOp(tok.line, tok.col, op=tok.value, left=left, right=right)
        return left

    def parse_add(self):
        left = self.parse_mul()
        while self.peek().kind == OP and self.peek().value in ("+", "-"):
            tok = self.next()
            right = self.parse_mul()
            left = A.BinOp(tok.line, tok.col, op=tok.value, left=left, right=right)
        return left

    def parse_mul(self):
        left = self.parse_unary()
        while self.peek().kind == OP and self.peek().value in ("*", "/", "%"):
            tok = self.next()
            right = self.parse_unary()
            left = A.BinOp(tok.line, tok.col, op=tok.value, left=left, right=right)
        return left

    def parse_unary(self):
        if self.peek().kind == OP and self.peek().value in ("-", "+"):
            tok = self.next()
            return A.UnaryOp(tok.line, tok.col, op=tok.value, operand=self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self):
        node = self.parse_primary()
        while self.at_op("["):
            tok = self.next()
            index = self.parse_expr()
            self.expect(OP, "]")
            node = A.HistRef(tok.line, tok.col, base=node, index=index, uid=self.new_uid())
        return node

    def parse_primary(self):
        tok = self.peek()

        if tok.kind == NUMBER:
            self.next()
            return A.Num(tok.line, tok.col, value=float(tok.value))
        if tok.kind == STRING:
            self.next()
            return A.Str(tok.line, tok.col, value=tok.value)
        if tok.kind == COLOR:
            self.next()
            return A.ColorLit(tok.line, tok.col, value=tok.value.upper())
        if tok.kind == OP and tok.value == "(":
            self.next()
            expr = self.parse_expr()
            self.expect(OP, ")")
            return expr
        if tok.kind == OP and tok.value == "[":
            self.next()
            items: list = []
            if not self.at_op("]"):
                items.append(self.parse_expr())
                while self.at_op(","):
                    self.next()
                    items.append(self.parse_expr())
            self.expect(OP, "]")
            return A.ListLit(tok.line, tok.col, items=items)
        if tok.kind == IDENT:
            if tok.value in ("true", "false"):
                self.next()
                return A.Bool(tok.line, tok.col, value=tok.value == "true")
            if tok.value == "na":
                self.next()
                # `na(x)` is a function call; bare `na` is the value
                if self.at_op("("):
                    return self._finish_call(tok)
                return A.Na(tok.line, tok.col)
            self.next()
            if self.at_op("("):
                return self._finish_call(tok)
            return A.Ident(tok.line, tok.col, name=tok.value)

        raise PineCompileError(f"unexpected {tok.value!r}", tok.line, tok.col)

    def _finish_call(self, name_tok: Token) -> A.Call:
        func = name_tok.value
        for prefix, msg in _UNSUPPORTED_CALLS.items():
            if func == prefix or func.startswith(prefix + "."):
                raise PineCompileError(msg, name_tok.line, name_tok.col)
        if func.startswith(("matrix.", "line.", "label.", "box.", "table.", "request.")):
            raise PineCompileError(
                f"{func.split('.')[0]}.* is not supported in this Pine subset",
                name_tok.line, name_tok.col)

        self.expect(OP, "(")
        args: list = []
        kwargs: dict = {}
        if not self.at_op(")"):
            while True:
                # keyword argument: IDENT = expr (but not ==)
                if (self.peek().kind == IDENT
                        and self.peek(1).kind == OP and self.peek(1).value == "="):
                    key = self.next().value
                    self.next()  # '='
                    kwargs[key] = self.parse_expr()
                else:
                    if kwargs:
                        tok = self.peek()
                        raise PineCompileError(
                            "positional argument after keyword argument",
                            tok.line, tok.col)
                    args.append(self.parse_expr())
                if self.at_op(","):
                    self.next()
                    continue
                break
        self.expect(OP, ")")
        return A.Call(name_tok.line, name_tok.col, func=func, args=args,
                      kwargs=kwargs, uid=self.new_uid())


def parse(src: str) -> A.Program:
    return Parser(src).parse()
