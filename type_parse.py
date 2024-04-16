#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Parsing the prototype JSIPCValue type output.

from ply import lex, yacc
from type_fx import AnyType, PrimitiveType, JSPropertyType, ObjectType, ArrayType, UnionType


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
        "boolean",
        "number",
        "any",
        "Array",
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

literals = "(){},?:;<>|"

precedence = [['left', '|']]


t_ignore = " \t\n\r"

def t_error(t):
    raise ParseError(t.lexpos, f'Bad character {t.value[0]}')


parserDebug = False
lex.lex(debug=parserDebug)

def p_JSType(p):
    """JSType : PrimitiveType
    | AnyType
    | ObjectType
    | ArrayType
    | JSType '|' JSType
    | '(' JSType ')'"""
    if len(p) == 2:
        p[0] = p[1]
    else:
        assert len(p) == 4
        if p[1] == '(':
            p[0] = p[2]
        else:
            tt = p[1].types if isinstance(p[1], UnionType) else [p[1]]
            tt.append(p[3])
            p[0] = UnionType(tt)

def p_PrimitiveType(p):
    """PrimitiveType : UNDEFINED
    | STRING
    | NULL
    | BOOLEAN
    | NUMBER"""
    p[0] = PrimitiveType(p[1])

def p_AnyType(p):
    """AnyType : ANY"""
    p[0] = AnyType()

def p_ObjectType(p):
    """ObjectType : '{' ObjectTypeInner '}'
    | '{' ObjectTypeInner FieldSeparator '}'
    | '{' '}'"""
    if len(p) == 4:
        p[0] = ObjectType(p[2])
    elif len(p) == 5:
        p[0] = ObjectType(p[2])
    else:
        p[0] = ObjectType([])

def p_FieldSeparator(p):
    """FieldSeparator : ','
    | ';'"""
    p[0] = p[1]

# This will definitely cause problems if we have a keyword as a key.
def p_Key(p):
    """Key : ID
    | INTEGER"""
    p[0] = p[1]

def p_ObjectTypeInner(p):
    """ObjectTypeInner : ObjectTypeInner FieldSeparator Key MaybeOptional JSType
    | Key MaybeOptional JSType"""
    if len(p) == 6:
        tt = p[1]
        tt.append(JSPropertyType(p[3], p[5], p[4]))
        p[0] = tt
    else:
        assert len(p) == 4
        p[0] = [JSPropertyType(p[1], p[3], p[2])]

def p_MaybeOptional(p):
    """MaybeOptional : '?' ':'
    | ':'"""
    if len(p) == 3:
        p[0] = True
    else:
        assert len(p) == 2
        p[0] = False

# XXX Change this to look like an actual JS array?
# XXX The newest version only supports a single type, so we can't really
# implement it as a Python array.
def p_ArrayType(p):
    """ArrayType : ARRAY '<' JSType '>'
    | ARRAY '<' '>'"""
    if len(p) == 5:
        p[0] = ArrayType(p[3])
    else:
        assert len(p) == 4
        p[0] = ArrayType(None)

def p_error(p):
    raise ParseError(p.lexpos, f'Syntax error at {p.value}')

yacc.yacc(write_tables=False)

def parseType(s):
    return yacc.parse(s, debug=parserDebug)