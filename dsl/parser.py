"""
DSL text → AST.

M1 decision (grammar.md §8): hand-written recursive descent, not lark/antlr —
the grammar is small and this keeps the toolchain dependency-free.

Pipeline: strip comments per line -> tokenize -> recursive-descent parse
into Program/Statement/OpCall/Ref/Quantity nodes (dsl/ast.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .ast import ASTValidationError, OpCall, Program, Quantity, Ref, Statement, validate_new_op

_UNITS = {"mm", "deg"}

_TOKEN_RE = re.compile(
    r"""
      (?P<NUMBER>   -?\d+(?:\.\d+)?)
    | (?P<IDENT>     [A-Za-z_]\w*)
    | (?P<STRING>    "(?:[^"\\]|\\.)*")
    | (?P<LPAREN>    \()
    | (?P<RPAREN>    \))
    | (?P<LBRACKET>  \[)
    | (?P<RBRACKET>  \])
    | (?P<COMMA>     ,)
    | (?P<EQUALS>    =)
    | (?P<DOT>       \.)
    | (?P<SEMI>      ;)
    | (?P<STAR>      \*)
    | (?P<SKIP>      \s+)
    | (?P<MISMATCH>  .)
    """,
    re.VERBOSE,
)


class ParseError(Exception):
    """Parse failure — counts against the parse-rate metric."""


@dataclass
class _Token:
    kind: str
    text: str
    line: int


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    lineno = 0
    for lineno, raw in enumerate(text.splitlines(), start=1):
        code = raw.split("#", 1)[0]  # strip comments
        for m in _TOKEN_RE.finditer(code):
            kind = m.lastgroup
            if kind == "SKIP":
                continue
            if kind == "MISMATCH":
                raise ParseError(f"unexpected character {m.group()!r} (line {lineno})")
            tokens.append(_Token(kind, m.group(), lineno))
    tokens.append(_Token("EOF", "", lineno + 1))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self, ahead: int = 0) -> _Token:
        return self._tokens[min(self._pos + ahead, len(self._tokens) - 1)]

    def _advance(self) -> _Token:
        tok = self._tokens[self._pos]
        if tok.kind != "EOF":
            self._pos += 1
        return tok

    def _expect(self, kind: str) -> _Token:
        tok = self._peek()
        if tok.kind != kind:
            raise ParseError(f"expected {kind}, got {tok.kind} {tok.text!r} (line {tok.line})")
        return self._advance()

    @staticmethod
    def _validate(op: str, args: dict) -> None:
        try:
            validate_new_op(op, args)
        except ASTValidationError as exc:
            raise ParseError(str(exc)) from exc

    # program ::= statement*
    def parse_program(self) -> Program:
        prog = Program()
        while self._peek().kind != "EOF":
            prog.statements.append(self._parse_statement())
        return prog

    # statement ::= feature_def | edit_op
    def _parse_statement(self) -> Statement:
        first = self._expect("IDENT")
        if self._peek().kind == "EQUALS":
            # feature_def ::= identifier "=" operation "(" args ")" ";"
            self._advance()
            op_tok = self._expect("IDENT")
            self._expect("LPAREN")
            args = self._parse_args("RPAREN")
            self._expect("RPAREN")
            self._expect("SEMI")
            self._validate(op_tok.text, args)
            return Statement(name=first.text, op=op_tok.text, args=args)

        # edit_op ::= operation "(" args ")" ";"  (first *is* the operation name)
        self._expect("LPAREN")
        args = self._parse_args("RPAREN")
        self._expect("RPAREN")
        self._expect("SEMI")
        self._validate(first.text, args)
        return Statement(name=None, op=first.text, args=args)

    # args ::= (key "=" value ("," key "=" value)*)?
    def _parse_args(self, end_kind: str) -> dict:
        args: dict = {}
        if self._peek().kind == end_kind:
            return args
        while True:
            key = self._expect("IDENT").text
            self._expect("EQUALS")
            args[key] = self._parse_value()
            if self._peek().kind == "COMMA":
                self._advance()
                continue
            break
        return args

    # value ::= number unit? | reference | string | "[" ... "]" | opcall
    def _parse_value(self):
        tok = self._peek()
        if tok.kind == "NUMBER":
            self._advance()
            unit = None
            if self._peek().kind == "IDENT" and self._peek().text in _UNITS:
                unit = self._advance().text
            return Quantity(value=float(tok.text), unit=unit)
        if tok.kind == "STRING":
            self._advance()
            return tok.text[1:-1].replace('\\"', '"')
        if tok.kind == "LBRACKET":
            return self._parse_bracket()
        if tok.kind == "IDENT":
            return self._parse_ident_value()
        raise ParseError(f"unexpected token {tok.kind} {tok.text!r} (line {tok.line})")

    def _parse_ident_value(self):
        path = [self._expect("IDENT").text]
        while self._peek().kind == "DOT":
            self._advance()
            path.append(self._expect("IDENT").text)

        if self._peek().kind == "LPAREN":
            # nested operation call, e.g. with=extrude(profile=hex_sk, length=200)
            if len(path) != 1:
                raise ParseError(f"operation name must not be dotted: {'.'.join(path)}")
            op = path[0]
            self._advance()
            args = self._parse_args("RPAREN")
            self._expect("RPAREN")
            self._validate(op, args)
            return OpCall(op=op, args=args)

        if self._peek().kind == "LBRACKET":
            # pattern-instance selector, e.g. pat1[*] / pat1[2] (grammar.md §5)
            self._advance()
            idx_tok = self._peek()
            if idx_tok.kind == "STAR":
                self._advance()
                index: str | int = "*"
            elif idx_tok.kind == "NUMBER" and "." not in idx_tok.text:
                self._advance()
                index = int(idx_tok.text)
            else:
                raise ParseError(f"expected * or an integer index (line {idx_tok.line})")
            self._expect("RBRACKET")
            return Ref(path=path, index=index)

        return Ref(path=path)

    # bracketed value: either a key=value list (e.g. circle=[center=origin, r=20])
    # or a plain list of bare values ("[" value* "]" in the formal grammar).
    def _parse_bracket(self):
        self._expect("LBRACKET")
        if self._peek().kind == "RBRACKET":
            self._advance()
            return []
        is_kv = self._peek().kind == "IDENT" and self._peek(1).kind == "EQUALS"
        if is_kv:
            args = self._parse_args("RBRACKET")
            self._expect("RBRACKET")
            return args
        values = [self._parse_value()]
        while self._peek().kind == "COMMA":
            self._advance()
            values.append(self._parse_value())
        self._expect("RBRACKET")
        return values


def parse(text: str) -> Program:
    """Parse DSL source into a Program.

    Returns:
        Program

    Raises:
        ParseError: on any syntax error, or a violated replace/pattern/
            mirror/constraint requirement (grammar.md §4.2).
    """
    return _Parser(_tokenize(text)).parse_program()


def parse_ref(token: str) -> Ref:
    """Parse a standalone reference token, e.g. body.face_top or pat1[*]."""
    tokens = _tokenize(token)
    parser = _Parser(tokens)
    value = parser._parse_ident_value()
    if not isinstance(value, Ref):
        raise ParseError(f"not a reference: {token!r}")
    if parser._peek().kind != "EOF":
        raise ParseError(f"trailing input after reference: {token!r}")
    return value
