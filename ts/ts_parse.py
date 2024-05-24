#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Parser for a subset of TypeScript.

from ply import lex, yacc
from ts import AnyType, NeverType, PrimitiveType, JSPropertyType, ObjectType, ArrayType, UnionType
import unittest
import re


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
        "nsIPrincipal",
        "BrowsingContext",
        "any",
        "never",
        "Array",
    )
)

tokens = [
    "ID",
    "INTEGER",
    "STRING_SINGLE",
    "STRING_DOUBLE",
    "ARROW",
] + [r.upper() for r in reserved]

# The (?!\d) means that the first character can't be a number.
def t_ID(t):
    r"(?!\d)[\w$]+"
    if t.value in reserved:
        t.type = t.value.upper()
    return t

def t_INTEGER(t):
    r"-?\d+"
    i = int(t.value)
    if i < -2147483648:
        raise ParseError(t.lexpos, f"Integer {i} is too small")
    if i > 2147483647:
        raise ParseError(t.lexpos, f"Integer {i} is too large")
    t.value = i
    return t

# XXX These probably need to escape everything, but I need to keep
# this in sync with JSActorMessageType::ObjectType::ToString().
# If I do that, it'll look more like
# import codecs
# t.value = codecs.decode(t.value[1:-1], "unicode-escape")

def t_STRING_SINGLE(t):
    r"'(?:[^'\\\n]|\\.)*'"
    t.value = t.value[1:-1].replace("\\'", "'")
    return t

def t_STRING_DOUBLE(t):
    r'"(?:[^"\\\n]|\\.)*"'
    t.value = t.value[1:-1].replace('\\"', '"')
    return t

def t_ARROW(t):
    r"=>"
    return t

literals = "(){},?:;<>|" + "="

precedence = [['left', '|']]


t_ignore = " \t\n\r"

def t_error(t):
    raise ParseError(t.lexpos, f'Bad character {t.value[0]}')


parserDebug = False
lex.lex(debug=parserDebug)

# Type declarations.

def p_JSType(p):
    """JSType : PrimitiveType
    | AnyType
    | NeverType
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
    | NUMBER
    | NSIPRINCIPAL
    | BROWSINGCONTEXT"""
    p[0] = PrimitiveType(p[1])

def p_AnyType(p):
    """AnyType : ANY"""
    p[0] = AnyType()

def p_NeverType(p):
    """NeverType : NEVER"""
    p[0] = NeverType()

def p_ObjectType(p):
    """ObjectType : '{' ObjectTypeInner '}'
    | '{' ObjectTypeInner PropertySeparator '}'
    | '{' '}'"""
    if len(p) == 4:
        p[0] = ObjectType(p[2])
    elif len(p) == 5:
        p[0] = ObjectType(p[2])
    else:
        p[0] = ObjectType([])

def p_PropertySeparator(p):
    """PropertySeparator : ','
    | ';'"""
    p[0] = p[1]

def p_PropertyName(p):
    """PropertyName : ID
    | ReservedPropertyName
    | INTEGER
    | STRING_SINGLE
    | STRING_DOUBLE"""
    p[0] = p[1]

# Our "reserved" words aren't reserved, so they can be used
# as names. This is a big hack to try to revert that.
def p_ReservedPropertyName(p):
    """ReservedPropertyName : UNDEFINED
    | STRING
    | NULL
    | BOOLEAN
    | NUMBER
    | NSIPRINCIPAL
    | BROWSINGCONTEXT
    | ANY
    | NEVER
    | ARRAY"""
    p[0] = p[1]

def p_ObjectTypeInner(p):
    """ObjectTypeInner : ObjectTypeInner PropertySeparator PropertyName MaybeOptional JSType
    | PropertyName MaybeOptional JSType"""
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

def p_ArrayType(p):
    """ArrayType : ARRAY '<' JSType '>'"""
    p[0] = ArrayType(p[3])

# Top level actor message declarations.

def p_TopLevelDecls(p):
    """TopLevelDecls : TopLevelActor
    | TopLevelActor ';'"""
    p[0] = p[1]

def p_TopLevelActor(p):
    """TopLevelActor : ID ID '=' '{' ActorDecls '}'"""
    if p[1] != "type":
        raise ParseError(p.lexpos, f'Expected actor declarations to start with "type", not "{p[1]}"')
    if p[2] != "MessageTypes":
        raise ParseError(p.lexpos, f'Expected pretend type name "MessageTypes", not "{p[2]}"')
    p[0] = p[5]

def p_ActorDecls(p) :
    """ActorDecls : ActorDeclsInner
    | ActorDeclsInner PropertySeparator"""
    p[0] = p[1]

def p_ActorDeclsInner(p) :
    """ActorDeclsInner : ActorDeclsInner PropertySeparator ActorDecl
    | ActorDecl"""
    if len(p) == 4:
        p[0] = p[1].append(p[2])
    else:
        assert len(p) == 2
        p[0] = [p[1]]

def p_ActorDecl(p) :
    """ActorDecl : ActorOrMessageName ':' '{' MessageDecls '}'"""
    p[0] = [p[1], p[4]]

def p_ActorOrMessageName(p):
    """ActorOrMessageName : ID
    | STRING_SINGLE
    | STRING_DOUBLE"""
    p[0] = p[1]

def p_MessageDecls(p):
    """MessageDecls : MessageDeclsInner
    | MessageDeclsInner PropertySeparator"""
    p[0] = p[1]

def p_MessageDeclsInner(p):
    """MessageDeclsInner : MessageDeclsInner MessageDecl PropertySeparator
    | MessageDecl"""
    if len(p) == 4:
        p[0] = p[1].append(p[2])
    else:
        assert len(p) == 2
        p[0] = [p[1]]

def p_MessageDecl(p):
    """MessageDecl : ActorOrMessageName ':' MessageType"""
    p[0] = [p[1], p[2]]

def p_MessageType(p):
    """MessageType : JSType
    | '(' ID ':' JSType ')' ARROW JSType
    """
    if len(p) == 2:
        # message kind Message
        p[0] = [p[1]]
    else:
        assert len(p) == 8
        t1 = p[4]
        t2 = p[7]
        isNever1 = NeverType() == t1
        isNever2 = NeverType() == t2
        if isNever1:
            if isNever2:
                # (_: never) => never;
                # I guess people can make empty declarations. Maybe it should
                # be an error.
                return []
            # (_: never) => T
            # message kind QueryResolve.
            return [NeverType(), NeverType(), t2]
        if isNever2:
            # (_: T) => never
            # message kind Query
            return [NeverType(), t1]
        raise ParseError(p.lexpos, 'Message type must have "never" to either the left or right of the arrow')


# Generic definitions.

def p_error(p):
    raise ParseError(p.lexpos, f'Syntax error at {p.value}')

typeParser = None

def parseType(s):
    global typeParser
    if typeParser is None:
        # This will generate a lot of warnings about the unused actor decls
        # rules, but that's okay.
        typeParser = yacc.yacc(start='JSType', write_tables=False)
    return typeParser.parse(s, debug=parserDebug)

actorDeclsParser = None

def parseActorDecls(s):
    global actorDeclsParser
    if actorDeclsParser is None:
        actorDeclsParser = yacc.yacc(start='TopLevelDecls', write_tables=False)
    return typeParser.parse(s, debug=parserDebug)


class BasicParseTests(unittest.TestCase):
    def parseAndCheck(self, s1):
        s2 = parseType(s1)
        self.assertEqual(s1, str(s2))

    def parseAndCheckFail(self, s):
        with self.assertRaises(ParseError):
            parseType(s)

    def test_basic(self):
        self.parseAndCheck("{whatever_$123: string}")
        self.parseAndCheckFail("{1whatever: string}")
        self.parseAndCheck("{\"https://*.example.com/*\": string}")
        self.parseAndCheck('{"\\t": string}')
        self.parseAndCheck('Array<never>')
        self.parseAndCheckFail('Array<>')

class TestPrinting(unittest.TestCase):
    def check(self, s, json):
        t = parseType(s)
        self.assertEqual(s, str(t))
        self.assertEqual(t.jsonStr(), json)

    def checkFail(self, s, error):
        with self.assertRaisesRegex(ParseError, re.escape(error)):
            parseType(s)

    def test_any_never(self):
        self.check("any", '"any"')
        self.check("never", '"never"')

    def test_primitive(self):
        self.check("undefined", '"undefined"')
        self.check("string", '"string"')
        self.check("undefined", '"undefined"')
        self.check("string", '"string"')
        self.check("null", '"null"')
        self.check("boolean", '"boolean"')
        self.check("number", '"number"')
        self.check("nsIPrincipal", '"nsIPrincipal"')
        self.check("BrowsingContext", '"BrowsingContext"')

    def test_array(self):
        self.check("Array<any>", '["array", "any"]')
        self.check("Array<never>", '["array", "never"]')
        self.check("Array<nsIPrincipal>", '["array", "nsIPrincipal"]')
        self.check("Array<Array<any>>", '["array", ["array", "any"]]')
        self.check("Array<Array<never>>", '["array", ["array", "never"]]')

    def test_union(self):
        self.check("any | any", '["union", "any", "any"]')
        # Do this in both orders to check that we aren't sorting.
        self.check("Array<never> | Array<any>", '["union", ["array", "never"], ["array", "any"]]')
        self.check("Array<any> | Array<never>", '["union", ["array", "any"], ["array", "never"]]')
        self.check("any | string | undefined",
                   '["union", ["union", "any", "string"], "undefined"]')

    def test_object(self):
        self.check("{}", '["object"]')
        self.check("{bar: Array<any>; foo: string}",
                   '["object", ["bar", ["array", "any"]], ["foo", "string"]]')
        self.check("{8: Array<any>; 12: string}",
                   '["object", [8, ["array", "any"]], [12, "string"]]')
        self.check("{foo: Array<any>; 12: string}",
                   '["object", ["foo", ["array", "any"]], [12, "string"]]')
        self.check("{-2147483648: any; 2147483647: any}",
                   '["object", [-2147483648, "any"], [2147483647, "any"]]')
        self.check("{x?: any; y: string}",
                   '["object", ["x", "any", true], ["y", "string"]]')
        # Our "reserved" words can be used as property names.
        self.check("{number: any}", '["object", ["number", "any"]]')

        self.checkFail("{-2147483649: any}", "Integer -2147483649 is too small")
        self.checkFail("{2147483648: any}", "Integer 2147483648 is too large")


if __name__ == "__main__":
    unittest.main()
