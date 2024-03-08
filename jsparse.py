#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# The world's worst JS parser. The goal is to parse JSON-y JS produced
# by JS_ValueToSource.

from ply import lex, yacc

tokens = [
    "PROPERTY",
    "INTEGER",
    "STRING",
    "TRUE",
    "FALSE"
]

def t_PROPERTY(t):
    r"[a-zA-Z][a-zA-Z0-9_]*"
    return t

def t_INTEGER(t):
    r"[1-9][0-9]*"
    t.value = int(t.value)
    return t

def t_STRING(t):
    r'"[^"]*"'
    t.value = t.value[1:-1]
    return t

def t_TRUE(t):
    r"true"
    t.value = True
    return t

def t_FALSE(t):
    r"false"
    t.value = False
    return t

literals = "{},:"

t_ignore = " \t"

def t_error(t):
    raise Exception(f'Bad character {t.value[0]}')

parserDebug = False
lex.lex(debug=parserDebug)

class JSMap:
    def __init__(self, m):
        self.map = m
    
def p_JSMap(p):
    """JSMap : '{' JSMapInner '}'"""
    p[0] = JSMap(p[2])

def p_JSMapInner(p):
    """JSMapInner : JSMapInner ',' PROPERTY ':' JSMapValue
    | PROPERTY ':' JSMapValue """
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

def p_JSMapValue(p):
    """JSMapValue : STRING
    | INTEGER
    | JSMap
    | TRUE
    | FALSE"""
    p[0] = p[1]

def p_error(p):
    print(f'Syntax error at "{p.value}"')

yacc.yacc(write_tables=False)

#s = '{type:"TOP_SITES_ORGANIC_IMPRESSION_STATS", data:{type:"impression", position:4, source:"newtab"}, meta:{from:"ActivityStream:Content", to:"ActivityStream:Main", skipLocal:true}}'
s = '{ position : 4 }'
for k, v in yacc.parse(s, debug=parserDebug).map.items():
    print(f'{k} --> {v}')

# {type:"TOP_SITES_ORGANIC_IMPRESSION_STATS", data:{type:"impression", position:4, source:"newtab"}, meta:{from:"ActivityStream:Content", to:"ActivityStream:Main", skipLocal:true}}

# ({type:"DISCOVERY_STREAM_LOADED_CONTENT", data:{source:"CARDGRID", tiles:[{id:3370035274971981, pos:0}]}, meta:{from:"ActivityStream:Content", to:"ActivityStream:Main"}})