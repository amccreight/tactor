#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Parsing the prototype JSIPCValue type output.

from ply import lex, yacc
from type_fx import AnyType, PrimitiveType, JSPropertyType, ObjectType, ArrayType, UnionType
import unittest


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
    | NUMBER
    | NSIPRINCIPAL
    | BROWSINGCONTEXT"""
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

# This will definitely cause problems if we have a keyword as a property name.
def p_PropertyName(p):
    """PropertyName : ID
    | INTEGER
    | STRING_SINGLE
    | STRING_DOUBLE"""
    p[0] = p[1]

def p_ObjectTypeInner(p):
    """ObjectTypeInner : ObjectTypeInner FieldSeparator PropertyName MaybeOptional JSType
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

# XXX Change this to look like an actual JS array?
# XXX The newest version only supports a single type, so we can't really
# implement it as a Python array.
def p_ArrayType(p):
    """ArrayType : ARRAY '<' JSType '>'
    | ARRAY '<' NEVER '>'"""
    if p[3] == "never":
        p[0] = ArrayType(None)
    else:
        p[0] = ArrayType(p[3])

def p_error(p):
    raise ParseError(p.lexpos, f'Syntax error at {p.value}')

yacc.yacc(write_tables=False)

def parseType(s):
    return yacc.parse(s, debug=parserDebug)

def basicTest():
    def parseAndCheck(s1):
        s2 = parseType(s1)
        print(f"{s1} --> {s2}")
        assert s1 == str(s2)
    def parseAndCheckFail(s):
        try:
            parseType(s)
            assert False
        except ParseError as p:
            return
    parseAndCheck("{whatever_$123: string}")
    parseAndCheckFail("{1whatever: string}")
    parseAndCheck("{\"https://*.example.com/*\": string}")
    parseAndCheck('{"\\t": string}')
    parseAndCheck('Array<never>')
    parseAndCheckFail('Array<>')


class TestPrinting(unittest.TestCase):
    def check(self, s, json):
        t = parseType(s)
        self.assertEqual(s, str(t))
        self.assertEqual(t.jsonStr(), json)

    def checkFail(self, s, error):
        try:
            parseType(s)
            assert False
        except ParseError as p:
            self.assertIn(error, str(p))

    def test_any(self):
        self.check("any", '"any"')

    def test_primitive(self):
        self.check("undefined", '["primitive", "undefined"]')
        self.check("string", '["primitive", "string"]')
        self.check("undefined", '["primitive", "undefined"]')
        self.check("string", '["primitive", "string"]')
        self.check("null", '["primitive", "null"]')
        self.check("boolean", '["primitive", "boolean"]')
        self.check("number", '["primitive", "number"]')
        self.check("nsIPrincipal", '["primitive", "nsIPrincipal"]')
        self.check("BrowsingContext", '["primitive", "BrowsingContext"]')

    def test_array(self):
        self.check("Array<any>", '["array", "any"]')
        self.check("Array<never>", '["array"]')
        self.check("Array<nsIPrincipal>", '["array", ["primitive", "nsIPrincipal"]]')
        self.check("Array<Array<any>>", '["array", ["array", "any"]]')
        self.check("Array<Array<never>>", '["array", ["array"]]')

    def test_union(self):
        self.check("any | any", '["union", "any", "any"]')
        # Do this in both orders to check that we aren't sorting.
        self.check("Array<never> | Array<any>", '["union", ["array"], ["array", "any"]]')
        self.check("Array<any> | Array<never>", '["union", ["array", "any"], ["array"]]')
        self.check("any | string | undefined",
                   '["union", ["union", "any", ["primitive", "string"]], ["primitive", "undefined"]]')

    def test_object(self):
        self.check("{}", '["object"]')
        self.check("{bar: Array<any>; foo: string}",
                   '["object", ["bar", ["array", "any"]], ["foo", ["primitive", "string"]]]')
        self.check("{8: Array<any>; 12: string}",
                   '["object", [8, ["array", "any"]], [12, ["primitive", "string"]]]')
        self.check("{foo: Array<any>; 12: string}",
                   '["object", ["foo", ["array", "any"]], [12, ["primitive", "string"]]]')
        self.check("{-2147483648: any; 2147483647: any}",
                   '["object", [-2147483648, "any"], [2147483647, "any"]]')
        self.check("{x?: any; y: string}",
                   '["object", ["x", "any", true], ["y", ["primitive", "string"]]]')

        self.checkFail("{-2147483649: any}", "Integer -2147483649 is too small")
        self.checkFail("{2147483648: any}", "Integer 2147483648 is too large")


if __name__ == "__main__":
    basicTest()

    unittest.main()
