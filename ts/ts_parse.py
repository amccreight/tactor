#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Parser for a subset of TypeScript.

from ply import lex, yacc
from actor_decls import Loc, kindToStr, ActorError, ActorDecls, ActorDecl, MessageTypes
from ts import AnyType, NeverType, PrimitiveType, JSPropertyType, ObjectType, ArrayType, UnionType
import json
import unittest
import re


class ParseError(Exception):
    def __init__(self, loc, msg):
        self.loc = loc
        self.error = f"{str(loc)}: {msg}"

    def __str__(self):
        return self.error

def _safeLinenoValue(t):
    lineno, value = 0, "???"
    if hasattr(t, "lineno"):
        lineno = t.lineno
    if hasattr(t, "value"):
        value = t.value
    return lineno, value

# XXX Bundle this state into a Parser structure like IPDL does?
currFilename = None

def locFromTok(p, num):
    return Loc(currFilename, p.lineno(num))

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

def t_newline(t):
    r"\n+"
    t.lexer.lineno += len(t.value)

literals = "(){},?:;<>|" + "="

precedence = [['left', '|']]


t_ignore = " \t\r"

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
    """TopLevelActor : ID ID '=' '{' ActorDecls '}' ';'"""
    if p[1] != "type":
        raise ParseError(locFromTok(p, 1),
                         f'Expected actor declarations to start with "type", not "{p[1]}"')
    if p[2] != "MessageTypes":
        raise ParseError(locFromTok(p, 2),
                         f'Expected top level type name to be "MessageTypes", not "{p[2]}"')
    p[0] = p[5]

def p_ActorDecls(p) :
    """ActorDecls : ActorDeclsInner
    | ActorDeclsInner PropertySeparator"""
    p[0] = p[1]

def p_ActorDeclsInner(p) :
    """ActorDeclsInner : ActorDeclsInner PropertySeparator ActorDecl
    | ActorDecl"""
    if len(p) == 4:
        actors = p[1]
        actors.addActorL(p[3])
        p[0] = actors
    else:
        assert len(p) == 2
        actors = ActorDecls()
        actors.addActorL(p[1])
        p[0] = actors

def p_ActorDecl(p) :
    """ActorDecl : ActorOrMessageName ':' '{' MessageDecls '}'"""
    actorDecl = p[4]
    [loc, actorName] = p[1]
    if isinstance(actorDecl, ActorDecl):
        actorDecl.loc = loc
        p[0] = [actorName, actorDecl]
    else:
        [loc, kind, messageName, loc0] = actorDecl
        raise ParseError(loc,
                         f'Multiple declarations of actor "{actorName}"\'s ' +
                         f'{kindToStr(kind)} message "{messageName}".' +
                         f' Previous was at {loc0}')

def p_ActorOrMessageName(p):
    """ActorOrMessageName : ID
    | STRING_SINGLE
    | STRING_DOUBLE"""
    p[0] = [locFromTok(p, 1), p[1]]

def p_MessageDecls(p):
    """MessageDecls : MessageDeclsInner
    | MessageDeclsInner PropertySeparator"""
    p[0] = p[1]

def p_MessageDeclsInner(p):
    """MessageDeclsInner : MessageDeclsInner PropertySeparator MessageDecl
    | MessageDecl"""
    if len(p) == 4:
        actorDecl = p[1]
        newDecl = p[3]
    else:
        assert len(p) == 2
        actorDecl = ActorDecl(Loc())
        newDecl = p[1]
    if actorDecl.addMessageL(newDecl):
        p[0] = actorDecl
    else:
        # Duplicate actor type declaration. Pass the data needed for an error
        # message back up to the point where we know what the actor is.
        [loc, messageName, _, kind] = newDecl
        loc0 = actorDecl.existingMessageKindLoc(messageName, kind)
        p[0] = [loc, kind, messageName, loc0]

def p_MessageDecl(p):
    """MessageDecl : ActorOrMessageName ':' MessageType"""
    p[0] = p[1] + p[3]

def p_MessageType(p):
    """MessageType : JSType
    | '(' ID ':' JSType ')' ARROW JSType
    """
    if len(p) == 2:
        # Message kind: Message.
        p[0] = [p[1], 0]
    else:
        assert len(p) == 8
        t1 = p[4]
        t2 = p[7]
        isNever1 = NeverType() == t1
        isNever2 = NeverType() == t2
        if isNever1:
            if isNever2:
                # (_: never) => never;
                # We could treat this as doing nothing, but that doesn't seem
                # like it is worth the hassle.
                raise ParseError(locFromTok(p, 1),
                                 'Message type must have a non-"never" type '
                                 'to either the left or right of the arrow')
            # (_: never) => T
            # Message kind: QueryResolve.
            # It is not possible to specify QueryReject.
            p[0] = [t2, 2]
            return
        if isNever2:
            # (_: T) => never
            # Message kind: Query.
            p[0] = [t1, 1]
            return
        # (_: T1) => T2
        raise ParseError(locFromTok(p, 1),
                         'Message type must have "never" to either the left ' +
                         'or right of the arrow')


# Generic definitions.

def p_error(p):
    lineno, value = _safeLinenoValue(p)
    raise ParseError(Loc(currFilename, lineno),
                     f'Syntax error near "{value}"')

lexer = None
typeParser = None

def parseType(s):
    global lexer
    if lexer is None:
        lexer = lex.lex(debug=parserDebug)
    global typeParser
    if typeParser is None:
        # This will generate a lot of warnings about the unused actor decls
        # rules, but that's okay.
        typeParser = yacc.yacc(start='JSType', write_tables=False)
    global currFilename
    currFilename = "type"
    lexer.lineno = 1
    return typeParser.parse(s, lexer=lexer, debug=parserDebug)

actorDeclsParser = None

def parseActorDecls(s, filename):
    global lexer
    if lexer is None:
        lexer = lex.lex(debug=parserDebug)
    global actorDeclsParser
    if actorDeclsParser is None:
        actorDeclsParser = yacc.yacc(start='TopLevelDecls', write_tables=False)
    global currFilename
    currFilename = filename
    lexer.lineno = 1
    return actorDeclsParser.parse(s, lexer=lexer, debug=parserDebug)


class BasicParseTests(unittest.TestCase):
    def parseAndCheck(self, s1):
        s2 = parseType(s1)
        self.assertEqual(s1, str(s2))

    def parseAndCheckFail(self, s, e):
        with self.assertRaisesRegex(ParseError, re.escape(e)):
            parseType(s)

    def test_basic(self):
        self.parseAndCheck("{whatever_$123: string}")
        self.parseAndCheckFail("{1whatever: string}", 'Syntax error near "whatever"')
        self.parseAndCheck("{\"https://*.example.com/*\": string}")
        self.parseAndCheck('{"\\t": string}')
        self.parseAndCheck('Array<never>')
        self.parseAndCheckFail('Array<>', 'Syntax error near ">"')

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

class ParseActorDeclsTests(unittest.TestCase):
    # The expected result is given as a Python JSON expression because that's
    # the simplest way to write down a big expression.
    def parseTest(self, x, y):
        self.assertEqual(json.loads(parseActorDecls(x, "test").toJSON()), y)

    def parseAndCheckFailP(self, s, e):
        with self.assertRaisesRegex(ParseError, re.escape(e)):
            parseActorDecls(s, "test")

    def parseAndCheckFail(self, s, e):
        with self.assertRaisesRegex(ActorError, re.escape(e)):
            parseActorDecls(s, "test")

    def test_basic_valid(self):
        # Testing support for multiple messages and actors.
        s = 'type MessageTypes = \n{ A: { M : any }; };'
        self.parseTest(s, {"A": {"M": ["any"]}})
        s = 'type MessageTypes = \n{ B: { M: number }, A: { M: undefined }; };'
        self.parseTest(s, {"A": {"M": ["undefined"]}, "B": {"M": ["number"]}})
        s = 'type MessageTypes = \n{ A: { N: any; M: undefined }; };'
        self.parseTest(s, {"A": {"M": ["undefined"], "N": ["any"]}})

        # Testing different message kinds.
        s = 'type MessageTypes = \n{ A: { M: boolean }; };'
        self.parseTest(s, {"A": {"M": ["boolean"]}})
        s = 'type MessageTypes = \n{ A: { M: (_: undefined) => never }; };'
        self.parseTest(s, {"A": {"M": ["never", "undefined"]}})
        s = 'type MessageTypes = \n{ A: { M: (_: never) => { x : boolean } }; };'
        self.parseTest(s, {"A": {"M": ["never", "never", ["object", ["x", "boolean"]]]}})
        s = ('type MessageTypes = \n{ A: { M: (_: never) => { x: boolean }; ' +
             'M:nsIPrincipal }; };')
        self.parseTest(s, {"A": {"M": ["nsIPrincipal", "never", ["object", ["x", "boolean"]]]}})
        s = ('type MessageTypes = \n{ A: { M: (_: never) => { x: boolean }; ' +
             'M:(_: boolean) => never }; };')
        self.parseTest(s, {"A": {"M": ["never", "boolean", ["object", ["x", "boolean"]]]}})
        s = ('type MessageTypes = \n{ A: { M: null, M: (_: never) => undefined; ' +
             'M:(_: number) => never }; };')
        self.parseTest(s, {"A": {"M": ["null", "number", "undefined"]}})

    def test_basic_fail(self):
        e = 'test:3: Expected actor declarations to start with "type", not "e"'
        self.parseAndCheckFailP("\n\ne f = { a: { m: any }; };", e)
        e = 'test:2: Expected top level type name to be "MessageTypes", not "e"'
        self.parseAndCheckFailP("type\n e = { a: { m: any }; };", e)
        # I'm not sure why this confuses it so much.
        self.parseAndCheckFailP("\n\neee", 'test:0: Syntax error near "???"')
        self.parseAndCheckFailP("\n\n1234", 'test:3: Syntax error near "1234"')

        # Multiple actor declarations, with various ways of writing actor names.
        s = 'type MessageTypes =\n { A: { M: any };\n A: { M: any}; };'
        e = 'test:3: Multiple declarations of actor "A". Previous was at test:2'
        self.parseAndCheckFail(s, e)
        s = 'type MessageTypes =\n { "A": { M: any };\n \'A\': { M: any}; };'
        e = 'test:3: Multiple declarations of actor "A". Previous was at test:2'
        self.parseAndCheckFail(s, e)
        s = 'type MessageTypes =\n { A: { M: any };\n "A": { M: any}; };'
        e = 'test:3: Multiple declarations of actor "A". Previous was at test:2'
        self.parseAndCheckFail(s, e)

        # Check various errors related to message kinds.
        s = 'type MessageTypes = \n{ A: { M: (_: any) => any }; };'
        e = 'test:2: Message type must have "never" to either the left or right of the arrow'
        self.parseAndCheckFailP(s, e)
        s = 'type MessageTypes = \n{ A: { M: (_: never) => never }; };'
        e = 'test:2: Message type must have a non-"never" type to either the left or right of the arrow'
        self.parseAndCheckFailP(s, e)
        s = 'type MessageTypes =\n { A: { M: any\n , M: any; };\n };'
        e = ('test:3: Multiple declarations of actor "A"\'s ' +
             'sendAsyncMessage() message "M". Previous was at test:2')
        self.parseAndCheckFailP(s, e)
        s = 'type MessageTypes =\n { A: { M: (_: any)=>never \n , M: (_: any)=>never; };\n };'
        e = ('test:3: Multiple declarations of actor "A"\'s ' +
             'sendQuery() message "M". Previous was at test:2')
        self.parseAndCheckFailP(s, e)
        s = 'type MessageTypes =\n { A: { M: (_: never)=>any \n , M: (_: never)=>any; };\n };'
        e = ('test:3: Multiple declarations of actor "A"\'s ' +
             'query reply message "M". Previous was at test:2')
        self.parseAndCheckFailP(s, e)


if __name__ == "__main__":
    unittest.main()
