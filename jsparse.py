#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# The world's worst JS parser. The goal is to parse JSON-y JS produced
# by JS_ValueToSource. Some of the Ply tricks in here are taken from
# Firefox's IPDL parser.

from ply import lex, yacc
from jsast import *


class ParseError(Exception):
    def __init__(self, loc, msg):
        self.loc = loc
        self.error = f"{str(loc)}: {msg}"

    def __str__(self):
        return self.error


# We're treating Infinity and NaN like reserved words, even though they aren't,
# which will cause problems if somebody tries to use them as a property.
reserved = set(
    (
        "false",
        "true",
        "null",
        "void",
        "Infinity",
        "NaN",
        "new",
    )
)

tokens = [
    "ID",
    "NUMBER",
    "STRING1",
    "STRING2",
    "REGEXP",
] + [r.upper() for r in reserved]

def t_ID(t):
    r"[a-zA-Z_][a-zA-Z0-9_]*"
    if t.value in reserved:
        t.type = t.value.upper()
    else:
        t.value = JSID(t.value)
    return t

# This doesn't deal with many of the ways you can write a number in JS,
# but hopefully it covers the important cases of JS_ValueToSource's output.
# This probably loses precision in various situations, but we don't actually
# care what the value is.
def t_NUMBER(t):
    r"-?\d+(?:[.]\d+(?:[Ee][+-]?\d+)?)?"
    if "." in t.value:
        t.value = float(t.value)
    else:
        t.value = int(t.value)
    return t

def t_STRING1(t):
    r"'(?:[^'\\\n]|\\.)*'"
    t.value = t.value[1:-1]
    return t

def t_STRING2(t):
    r'"(?:[^"\\\n]|\\.)*"'
    t.value = t.value[1:-1]
    return t

def t_REGEXP(t):
    r"/(?:[^/\\\n]|\\.)*/"
    t.value = JSRegExp(t.value[1:-1])
    return t

literals = "(){}[],:"

t_ignore = " \t\n\r"

def t_error(t):
    raise ParseError(t.lexpos, f'Bad character {t.value[0]}')

parserDebug = False
lex.lex(debug=parserDebug)

def p_JSValue(p):
    """JSValue : '(' JSValue ')'
    | JSMap
    | JSArray
    | String
    | NUMBER
    | INFINITY
    | NAN
    | REGEXP
    | Bool
    | NULL
    | VOID NUMBER
    | NEW ID '(' FunArgs ')'"""
    if len(p) == 2:
        if p[1] == "null":
            p[0] = JSNull()
        elif p[1] == "Infinity":
            p[0] = JSInfinity()
        elif p[1] == "NaN":
            p[0] = JSNaN()
        else:
            p[0] = p[1]
    elif len(p) == 4:
        p[0] = p[2]
    elif len(p) == 3:
        p[0] = JSUndefined()
    elif len(p) == 6:
        p[0] = JSBuiltin(p[2].name)
    else:
        assert False

def p_FunArgs(p):
    """FunArgs : JSValue
    | JSValue ',' FunArgs
    | """
    if len(p) == 2:
        p[0] = [p[1]]
    elif len(p) == 4:
        p[0] = [p[1]] + p[3]
    else:
        assert len(p) == 1
        p[0] = []

def p_String(p):
    """String : STRING1
    | STRING2"""
    p[0] = p[1]

def p_JSMap(p):
    """JSMap : '{' JSMapInner '}'
    | '{' '}'"""
    if len(p) == 4:
        p[0] = p[2]
    else:
        p[0] = {}

def p_Label(p):
    """Label : ID
    | String
    | NUMBER
    | NEW"""
    if p[1] == "new":
        # Reserved words can be used as object properties. Thanks, Javascript.
        p[0] = "new"
    else:
        p[0] = p[1]

def p_JSMapInner(p):
    """JSMapInner : JSMapInner ',' Label ':' JSValue
    | Label ':' JSValue """
    if len(p) == 6:
        m = p[1]
        prop = p[3]
        v = p[5]
        assert not prop in m
        m[prop] = v
        p[0] = m
    else:
        m = {}
        m[p[1]] = p[3]
        p[0] = m

def p_JSArray(p):
    """JSArray : '[' JSArrayInner ']'"""
    p[0] = p[2]

def p_JSArrayInner(p):
    """JSArrayInner :
    | JSValue
    | JSValue ',' JSArrayInner"""
    if len(p) == 1:
        p[0] = []
    elif len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = [p[1]] + p[3]

def p_Bool(p):
    """Bool : TRUE
    | FALSE"""
    p[0] = p[1] == "true"

def p_error(p):
    raise ParseError(p.lexpos, f'Syntax error at {p.value}')

yacc.yacc(write_tables=False)


def testTypeScriptParsing():
    def parseTS(s):
        return yacc.parse(s, debug=parserDebug)
    def simpleParseAndLog(s):
        print(jsToString(parseTS(s)))
        print()
    # Some basic parsing tests.
    simpleParseAndLog('Infinity')
    simpleParseAndLog("{re:/blah blah\(\/ whatever/}")
    simpleParseAndLog("{'blah':true}")
    simpleParseAndLog('"\\""')
    simpleParseAndLog('"str\\"ing"')
    simpleParseAndLog('"str\\"in\\"g"')
    simpleParseAndLog('{x:"string", y:"bar"}')
    simpleParseAndLog('-0.8426605824886742\n')
    simpleParseAndLog('-100')
    simpleParseAndLog('null')
    simpleParseAndLog('(void 0)')
    simpleParseAndLog('{}')
    simpleParseAndLog('({ position : [], foo : [1,2,] , bar: [2,3] })')
    simpleParseAndLog('{ position : [12, 13, {blahblah:1234}] }')
    simpleParseAndLog('{ position : [{id:1234567890, pos:0}, 12, false] }')

    simpleParseAndLog('{ position : [{id:1234567890, pos:0}, 12, false] }')

    simpleParseAndLog('{ position : 4 }')
    simpleParseAndLog('{ position : true }')
    s = '{type:"TOP_SITES_ORGANIC_IMPRESSION_STATS", data:{type:"impression", position:4, source:"newtab"}, meta:{from:"ActivityStream:Content", to:"ActivityStream:Main", skipLocal:true}}'
    simpleParseAndLog(s)
    s = '{type:"DISCOVERY_STREAM_LOADED_CONTENT", data:{source:"CARDGRID", tiles:[{id:1234567890, pos:0}]}, meta:{from:"ActivityStream:Content", to:"ActivityStream:Main"}}'
    simpleParseAndLog(s)


if __name__ == "__main__":
    testTypeScriptParsing()
