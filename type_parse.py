#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Parsing the prototype JSIPCValue type output.

from ply import lex, yacc


class ParseError(Exception):
    def __init__(self, loc, msg):
        self.loc = loc
        self.error = f"{str(loc)}: {msg}"

    def __str__(self):
        return self.error

reserved = set(
    (
        "undefined",
        "string",
        "null",
        "bool",
        "number",
        "Any",
        "ArrayType",
        "Union",
    )
)

tokens = [
    "ID",
    "INTEGER",
] + [r.upper() for r in reserved]

# TODO: object properties can be any valid string, including things
# with spaces or reserved words, so I should change the logging to wrap
# them in quotes. I'll also have to deal with quote escaping, like I did
# in my JS parser.
def t_ID(t):
    r"[a-zA-Z_][a-zA-Z0-9_-]*"
    if t.value in reserved:
        t.type = t.value.upper()
    return t

# This is only positive integers, which we need for array properties.
def t_INTEGER(t):
    r"\d+"
    t.value = int(t.value)
    return t

# XXX Maybe I'll use [] for arrays to be less weird.
literals = "(){},:"

t_ignore = " \t\n\r"

def t_error(t):
    raise ParseError(t.lexpos, f'Bad character {t.value[0]}')


parserDebug = False
lex.lex(debug=parserDebug)

def p_JSType(p):
    """JSType : UNDEFINED
    | STRING
    | NULL
    | BOOL
    | NUMBER
    | ANY
    | JSObject
    | JSArray
    | Union"""
    p[0] = p[1]

def p_JSObject(p):
    """JSObject : '{' JSObjectInner '}'
    | '{' JSObjectInner ',' '}'
    | '{' '}'"""
    if len(p) == 4:
        p[0] = p[2]
    elif len(p) == 5:
        p[0] = p[2]
    else:
        p[0] = {}

# This will definitely cause problems if we have a keyword as a key.
def p_Key(p):
    """Key : ID
    | INTEGER"""
    p[0] = p[1]

def p_JSObjectInner(p):
    """JSObjectInner : JSObjectInner ',' Key ':' JSType
    | Key ':' JSType"""
    if len(p) == 6:
        m = p[1]
        k = p[3]
        v = p[5]
        assert not k in m
        m[k] = v
        p[0] = m
    else:
        assert len(p) == 4
        m = {}
        m[p[1]] = p[3]
        p[0] = m

# XXX Change this to look like an actual JS array?
# XXX The newest version only supports a single type, so we can't really
# implement it as a Python array.
def p_JSArray(p):
    """JSArray : ARRAYTYPE '(' JSArrayInner ')'
    | ARRAYTYPE '(' JSArrayInner ',' ')'
    | ARRAYTYPE '(' ')' """
    if len(p) == 5:
        p[0] = p[3]
    elif len(p) == 6:
        p[0] = p[3]
    else:
        assert len(p) == 4
        p[0] = []

def p_JSArrayInner(p):
    """JSArrayInner : JSType
    | JSArrayInner ',' JSType"""
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        assert len(p) == 4
        p[1].append(p[3])
        p[0] = p[1]

# XXX I shouldn't represent both this and arrays
# as a Python array.
def p_Union(p):
    """Union : UNION '(' UnionInner ')'
    | UNION '(' UnionInner ',' ')'
    | UNION '(' ')' """
    if len(p) == 5:
        p[0] = p[3]
    elif len(p) == 6:
        p[0] = p[3]
    else:
        assert len(p) == 4
        p[0] = []

def p_UnionInner(p):
    """UnionInner : JSType
    | UnionInner ',' JSType"""
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        assert len(p) == 4
        p[1].append(p[3])
        p[0] = p[1]

def p_error(p):
    raise ParseError(p.lexpos, f'Syntax error at {p.value}')

yacc.yacc(write_tables=False)

def parseType(s):
    return yacc.parse(s, debug=parserDebug)