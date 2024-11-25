#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Tests for the JS actor message type Python infrastructure. These
# are combined into a single file because the easiest way to write
# tests usually involves the parser, which means tests can depend
# on a lot of other files.

import json
import re
import unittest

from actor_decls import (
    ActorDecl,
    ActorDecls,
    ActorError,
    Loc,
    MessageTypes,
)
from ts import (
    AnyType,
    ArrayOrSetType,
    JSPropertyType,
    MapType,
    NeverType,
    ObjectType,
    PrimitiveType,
    UnionType,
    primitiveTypes,
    tryUnionWith,
    unionWith,
)
from ts_parse import (
    ActorDeclsParser,
    TypeParser,
)


# Tests for combining types together.
class TestUnion(unittest.TestCase):
    def test_basic(self):
        t1 = ObjectType(
            [
                JSPropertyType("x", PrimitiveType("undefined"), False),
                JSPropertyType("y", PrimitiveType("number"), False),
            ]
        )
        t2 = ObjectType([JSPropertyType("x", PrimitiveType("boolean"), False)])
        self.assertEqual(
            str(tryUnionWith(t1, t2)), "{x: boolean | undefined; y?: number}"
        )

        t1 = ObjectType([JSPropertyType("x", PrimitiveType("undefined"), False)])
        t2 = ObjectType(
            [
                JSPropertyType("a", PrimitiveType("number"), False),
                JSPropertyType("x", AnyType(), False),
            ]
        )
        self.assertEqual(str(tryUnionWith(t1, t2)), "{a?: number; x: any}")

        t1 = ObjectType(
            [
                JSPropertyType(
                    "x",
                    UnionType([PrimitiveType("null"), PrimitiveType("string")]),
                    False,
                )
            ]
        )
        t2 = ObjectType(
            [
                JSPropertyType(
                    "x",
                    UnionType([PrimitiveType("null"), PrimitiveType("string")]),
                    False,
                )
            ]
        )
        self.assertEqual(str(tryUnionWith(t1, t2)), "{x: null | string}")

        self.assertEqual(str(ArrayOrSetType(True, NeverType())), "Array<never>")
        self.assertEqual(str(ArrayOrSetType(False, NeverType())), "Set<never>")
        self.assertEqual(
            str(MapType(PrimitiveType("number"), NeverType())), "Map<number, never>"
        )

        self.assertEqual(
            str(tryUnionWith(NeverType(), PrimitiveType("number"))), "number"
        )
        self.assertEqual(
            str(tryUnionWith(PrimitiveType("number"), NeverType())), "number"
        )


class BasicParseTests(unittest.TestCase):
    def __init__(self, methodName):
        unittest.TestCase.__init__(self, methodName)
        self.parser = TypeParser()

    def parseAndCheck(self, s1):
        s2 = self.parser.parse(s1)
        self.assertEqual(s1, str(s2))

    def parseAndCheckFail(self, s, e):
        with self.assertRaisesRegex(ActorError, re.escape(e)):
            self.parser.parse(s)

    def test_basic(self):
        self.parseAndCheck("{whatever_$123: string}")
        self.parseAndCheckFail("{1whatever: string}", 'Syntax error near "whatever"')
        self.parseAndCheck('{"https://*.example.com/*": string}')
        self.parseAndCheck('{"\\t": string}')
        self.parseAndCheck("Array<never>")
        self.parseAndCheckFail("Array<>", 'Syntax error near ">"')
        self.parseAndCheck("Set<never>")
        self.parseAndCheckFail("Set<>", 'Syntax error near ">"')
        self.parseAndCheck("Map<never, never>")
        self.parseAndCheckFail("Map<>", 'Syntax error near ">"')


# Tests for the two possible type outputs, TypeScript and JSON.
class TestTypePrinting(unittest.TestCase):
    def __init__(self, methodName):
        unittest.TestCase.__init__(self, methodName)
        self.parser = TypeParser()

    def check(self, s, json):
        t = self.parser.parse(s)
        self.assertEqual(s, str(t))
        self.assertEqual(t.jsonStr(), json)

    # Similar to check, except the expected string is explicitly specified.
    def checkString(self, input, expected, json):
        t = self.parser.parse(input)
        self.assertEqual(expected, str(t))
        self.assertEqual(t.jsonStr(), json)

    def checkFail(self, s, error):
        with self.assertRaisesRegex(ActorError, re.escape(error)):
            self.parser.parse(s)

    def test_basic(self):
        # any, never, testOnly
        self.check("any", '"any"')
        self.check("never", '"never"')
        self.check("testOnly", '"testOnly"')

        # comments
        self.checkString("any //", "any", '"any"')
        self.checkString("any // comment", "any", '"any"')
        self.checkString("//\nany", "any", '"any"')
        self.checkString("/* comment */any", "any", '"any"')
        self.checkString("/*\n/*\n**/any", "any", '"any"')

        # primitive types
        for p in primitiveTypes:
            self.check(p, f'"{p}"')

        # Array
        self.check("Array<any>", '["array", "any"]')
        self.check("Array<never>", '["array", "never"]')
        self.check("Array<testOnly>", '["array", "testOnly"]')
        self.check("Array<nsIPrincipal>", '["array", "nsIPrincipal"]')
        self.check("Array<Array<any>>", '["array", ["array", "any"]]')
        self.check("Array<Array<never>>", '["array", ["array", "never"]]')

        # Set
        self.check("Set<any>", '["set", "any"]')
        self.check("Set<never>", '["set", "never"]')
        self.check("Set<nsIPrincipal>", '["set", "nsIPrincipal"]')
        self.check("Set<Set<any>>", '["set", ["set", "any"]]')
        self.check("Set<Set<never>>", '["set", ["set", "never"]]')

        # Map
        self.check("Map<any, number>", '["map", "any", "number"]')
        self.check("Map<never, any>", '["map", "never", "any"]')
        self.check("Map<nsIPrincipal, number>", '["map", "nsIPrincipal", "number"]')
        self.check(
            "Map<Map<any, never>, number>", '["map", ["map", "any", "never"], "number"]'
        )

        # union
        self.check("any | any", '["union", "any", "any"]')
        # Do this in both orders to check that we are sorting in the TS output,
        # but not JSON output.
        self.checkString(
            "Array<never> | Array<any>",
            "Array<any> | Array<never>",
            '["union", ["array", "never"], ["array", "any"]]',
        )
        self.check(
            "Array<any> | Array<never>",
            '["union", ["array", "any"], ["array", "never"]]',
        )
        self.checkString(
            "Set<never> | Set<any>",
            "Set<any> | Set<never>",
            '["union", ["set", "never"], ["set", "any"]]',
        )
        self.check(
            "Set<any> | Set<never>",
            '["union", ["set", "any"], ["set", "never"]]',
        )
        self.check(
            "any | string | undefined",
            '["union", ["union", "any", "string"], "undefined"]',
        )
        # Unary union, which can occur in Prettier output.
        self.checkString("| any", "any", '"any"')
        self.checkString(
            "| any | boolean", "any | boolean", '["union", "any", "boolean"]'
        )

        # object
        self.check("{}", '["object"]')
        self.check(
            "{bar: Array<any>; foo: string}",
            '["object", ["bar", ["array", "any"]], ["foo", "string"]]',
        )
        self.check(
            "{8: Array<any>; 12: string}",
            '["object", [8, ["array", "any"]], [12, "string"]]',
        )
        self.check(
            "{foo: Array<any>; 12: string}",
            '["object", ["foo", ["array", "any"]], [12, "string"]]',
        )
        self.check(
            "{-2147483648: any; 2147483647: any}",
            '["object", [-2147483648, "any"], [2147483647, "any"]]',
        )
        self.check(
            "{x?: any; y: string}", '["object", ["x", "any", true], ["y", "string"]]'
        )
        # Our "reserved" words can be used as property names.
        self.check("{number: any}", '["object", ["number", "any"]]')

        self.checkFail("{-2147483649: any}", "Integer -2147483649 is too small")
        self.checkFail("{2147483648: any}", "Integer 2147483648 is too large")


class ParseActorDeclsTests(unittest.TestCase):
    def __init__(self, methodName):
        unittest.TestCase.__init__(self, methodName)
        self.parser = ActorDeclsParser()

    # The expected result is given as a Python JSON expression because that's
    # the simplest way to write down a big expression.
    def parseTest(self, x, y):
        self.assertEqual(json.loads(self.parser.parse(x, "test").toJSON()), y)

    def parseAndCheckFail(self, s, e):
        with self.assertRaisesRegex(ActorError, re.escape(e)):
            self.parser.parse(s, "test")

    def test_basic_valid(self):
        # Testing support for multiple messages and actors.
        s = "type MessageTypes = \n{ A: { M : any }; };"
        self.parseTest(s, {"A": {"M": ["any"]}})
        s = "type MessageTypes = //ok\n{ B: { M: number }, A1_$A: { 'M1:m_': undefined }; };"
        self.parseTest(s, {"A1_$A": {"M1:m_": ["undefined"]}, "B": {"M": ["number"]}})
        s = 'type MessageTypes = \n{ AB3: /*yes*/ { N: any; "M1:-m": undefined }; };'
        self.parseTest(s, {"AB3": {"M1:-m": ["undefined"], "N": ["any"]}})

        # Testing different message kinds.
        s = "type MessageTypes = \n{ a: { m: boolean }; };"
        self.parseTest(s, {"a": {"m": ["boolean"]}})
        s = "type MessageTypes = \n{ A: { M: (_: undefined) => never }; };"
        self.parseTest(s, {"A": {"M": ["undefined", "never"]}})
        s = "type MessageTypes = \n{ A: { M: (_: never) => { x : boolean } }; };"
        self.parseTest(s, {"A": {"M": ["never", ["object", ["x", "boolean"]]]}})
        s = "type MessageTypes = \n{ A: { M: (_: undefined) => boolean }; };"
        self.parseTest(s, {"A": {"M": ["undefined", "boolean"]}})

        # Single-type actors.
        s = "type MessageTypes = \n{ a: any, b: testOnly };"
        self.parseTest(s, {"a": "any", "b": "testOnly"})

    def test_basic_fail(self):
        e = 'test:3: Expected actor declarations to start with "type", not "e"'
        self.parseAndCheckFail("/*\n ok*/\ne f = { a: { m: any }; };", e)
        e = 'test:2: Expected top level type name to be "MessageTypes", not "e"'
        self.parseAndCheckFail("type\n e = { a: { m: any }; };", e)
        # I'm not sure why this confuses it so much.
        self.parseAndCheckFail("\n\neee", 'test:0: Syntax error near "???"')
        self.parseAndCheckFail("\n\n1234", 'test:3: Syntax error near "1234"')

        # Restrictions on actor names.
        def badActorName(name):
            s = f"type MessageTypes =\n {{ '{name}': {{ M: any }}; }};"
            e = f'test:2: Actor name "{name}" should be a valid identifier'
            self.parseAndCheckFail(s, e)

        badActorName("A B")
        badActorName("3A")
        badActorName("A:B")
        badActorName("A-B")

        # Restrictions on message names.
        def badMessageName(name):
            s = f"type MessageTypes =\n {{ M: {{ '{name}': any }}; }};"
            e = f'test:2: Message name "{name}" should be a valid identifier'
            self.parseAndCheckFail(s, e)

        badMessageName("M ")
        badMessageName("3M")
        badMessageName("-M")
        badMessageName(":M")

        # Multiple actor declarations, with various ways of writing actor names.
        s = "type MessageTypes =\n { A: { M: any };\n A: { M: any}; };"
        e = "test:3: Multiple declarations of actor A. Previous was at test:2"
        self.parseAndCheckFail(s, e)
        s = "type MessageTypes =\n { \"A\": { M: any };\n 'A': { M: any}; };"
        e = "test:3: Multiple declarations of actor A. Previous was at test:2"
        self.parseAndCheckFail(s, e)
        s = 'type MessageTypes =\n { A: { M: any };\n "A": { M: any}; };'
        e = "test:3: Multiple declarations of actor A. Previous was at test:2"
        self.parseAndCheckFail(s, e)

        # Need to have at least one non-never type for a query.
        s = "type MessageTypes = \n{ A: { M: (_: never) => never }; };"
        e = 'test:2: Message type must have a non-"never" type to either the left or right of the arrow'
        self.parseAndCheckFail(s, e)

        # Single-type actors can only be `any` or `testOnly`.
        s = "type MessageTypes = \n{ a: boolean };"
        e = 'test:2: Syntax error near "boolean"'
        self.parseAndCheckFail(s, e)

        # Multiple messages
        s = "type MessageTypes =\n { A: { M: any\n , M: any; };\n };"
        e = (
            "test:3: Multiple declarations of message M for actor A. "
            + "Previous was at test:2"
        )
        self.parseAndCheckFail(s, e)
        s = "type MessageTypes =\n { A: { M: any\n , M: (_: never) => any; };\n };"
        e = (
            "test:3: Multiple declarations of message M for actor A. "
            + "Previous was at test:2"
        )
        self.parseAndCheckFail(s, e)

        # Multiple messages followed by another message. Error propagation
        # works differently in this case.
        s = "type MessageTypes =\n { A: {\n M: any\n , M: any; N: any};\n };"
        e = (
            "test:4: Multiple declarations of message M for actor A. "
            + "Previous was at test:3"
        )
        self.parseAndCheckFail(s, e)


class TestTypeUnion(unittest.TestCase):
    def __init__(self, methodName):
        unittest.TestCase.__init__(self, methodName)
        self.parser = TypeParser()

    def test_union(self):
        # With these larger types, it is easier to write tests when we have
        # the parser. This doesn't feel like the right place for this, though.

        def unionWithTypes(types):
            t = NeverType()
            for tString in types:
                t = unionWith(t, self.parser.parse(tString))
            return t

        # A type can productively combine with multiple types in a union.
        types = [
            "{A: any}",
            "{B: any}",
            "{A: any; B: any}",
        ]
        self.assertEqual(str(unionWithTypes(types)), "{A?: any; B?: any}")

        types = [
            "{A: any} | {B: any}",
            "{A: any; B: any} | number",
        ]
        self.assertEqual(str(unionWithTypes(types)), "number | {A?: any; B?: any}")

    def test_simplify(self):
        # The C++ inference now produces non-canonical types. These should get
        # canonicalized when we run simplify on them.

        def assertSimplifies(tString, expected):
            t = self.parser.parse(tString)
            t = t.simplify()
            self.assertEqual(str(t), expected)

        t1 = "{A: any} | {A: any; B: any} | {C: any}"
        t2 = "{A: any; B?: any} | {C: any}"
        assertSimplifies(t1, t2)

        t1 = "number | " + t1
        t2 = "number | " + t2
        assertSimplifies(t1, t2)

        t1 = "number | {C: any}"
        assertSimplifies(t1, t1)

        # Test that we simplify through various nested unions and arrays.
        t1 = "Array<Array<{A: any} | {A: any; B: any}> | number>"
        t2 = "Array<Array<{A: any; B?: any}> | number>"
        assertSimplifies(t1, t2)

        # Test that we simplify both keys and values of nested maps.
        inner1 = "Map<{A: any} | {A: any; B: any}, number> | number"
        t1 = "Map<" + inner1 + ", " + inner1 + ">"
        inner2 = "Map<{A: any; B?: any}, number> | number"
        t2 = "Map<" + inner2 + ", " + inner2 + ">"
        assertSimplifies(t1, t2)

        # Test that we simplify types in object types.
        t1 = "{C: {A: any} | {A: any; B: any}}"
        t2 = "{C: {A: any; B?: any}}"
        assertSimplifies(t1, t2)

        # simplify() should not create unions with only one type.
        tAnyOrAny = self.parser.parse("any | any")
        tAnyOrAny = tAnyOrAny.simplify()
        self.assertEqual(tAnyOrAny.jsonStr(), "any")


class MessageTests(unittest.TestCase):
    def test_messageTypes(self):
        # sendAsyncMessage
        mt = MessageTypes(Loc(), [AnyType()])
        self.assertEqual(json.loads(mt.toJSON()), ["any"])
        self.assertEqual(mt.toTS("x"), "x: any;\n")

        # query
        mt = MessageTypes(Loc(), [AnyType(), None])
        self.assertEqual(json.loads(mt.toJSON()), ["any", "never"])
        self.assertEqual(mt.toTS("x"), "x: (_: any) => never;\n")

        # query resolve
        mt = MessageTypes(Loc(), [None, AnyType()])
        self.assertEqual(
            json.loads(mt.toJSON()),
            [
                "never",
                "any",
            ],
        )
        self.assertEqual(mt.toTS("x"), "x: (_: never) => any;\n")

        # query and query resolve
        mt = MessageTypes(Loc(), [PrimitiveType("undefined"), AnyType()])
        self.assertEqual(
            json.loads(mt.toJSON()),
            [
                "undefined",
                "any",
            ],
        )
        self.assertEqual(mt.toTS("x"), "x: (_: undefined) => any;\n")

    def test_messageDecls(self):
        ad = ActorDecl(Loc())
        self.assertEqual(ad.addMessage(Loc(), "M2", [AnyType()]), True)
        self.assertEqual(json.loads(ad.toJSON()), {"M2": ["any"]})
        self.assertEqual(ad.toTS(), "{\n  M2: any;\n};\n")
        self.assertEqual(ad.addMessage(Loc(), "M1", [None, AnyType()]), True)
        self.assertEqual(
            json.loads(ad.toJSON()), {"M1": ["never", "any"], "M2": ["any"]}
        )
        self.assertEqual(ad.toTS(), "{\n  M1: (_: never) => any;\n  M2: any;\n};\n")
        # Adding a message twice fails.
        self.assertEqual(ad.addMessage(Loc(), "M2", [AnyType()]), False)
        self.assertEqual(ad.addMessage(Loc(), "M2", [AnyType(), None]), False)

        # Name that needs quotes.
        ad = ActorDecl(Loc())
        self.assertEqual(ad.addMessage(Loc(), "A1:M1", [AnyType()]), True)
        self.assertEqual(json.loads(ad.toJSON()), {"A1:M1": ["any"]})
        self.assertEqual(ad.toTS(), '{\n  "A1:M1": any;\n};\n')

    def test_actorDecls(self):
        ads = ActorDecls()
        self.assertEqual(json.loads(ads.toJSON()), {})
        ads.addActor("B", ActorDecl(Loc()))
        self.assertEqual(json.loads(ads.toJSON()), {"B": {}})
        with self.assertRaisesRegex(ActorError, "Multiple declarations of actor B."):
            ads.addActor("B", ActorDecl(Loc()))
        ads.addMessage(Loc(), "B", "M", [AnyType()])
        self.assertEqual(json.loads(ads.toJSON()), {"B": {"M": ["any"]}})
        e = "Multiple declarations of message M for actor B."
        with self.assertRaisesRegex(ActorError, re.escape(e)):
            ads.addMessage(Loc(), "B", "M", [AnyType(), None])
        ads.addActor("A", ActorDecl(Loc()))
        ads.addMessage(Loc(), "A", "M", [AnyType()])
        self.assertEqual(
            json.loads(ads.toJSON()), {"A": {"M": ["any"]}, "B": {"M": ["any"]}}
        )
        self.assertEqual(
            ads.toTS(),
            "type MessageTypes = {\n"
            + "  A: {\n    M: any;\n  };\n"
            + "  B: {\n    M: any;\n  };\n"
            + "};\n",
        )

        # Basic tests for addActors
        ads = ActorDecls()
        ads.addActor("B", ActorDecl(Loc()))
        ads.addMessage(Loc(), "B", "M", [AnyType()])
        ads2 = ActorDecls()
        ads.addActor("A", ActorDecl(Loc()))
        ads.addMessage(Loc(), "A", "M", [AnyType()])
        ads.addActor("C", ActorDecl(Loc()))
        ads.addMessage(Loc(), "C", "M", [AnyType()])
        ads.addActors(ads2)
        self.assertEqual(
            json.loads(ads.toJSON()),
            {"A": {"M": ["any"]}, "B": {"M": ["any"]}, "C": {"M": ["any"]}},
        )

        ads = ActorDecls()
        ads.addActor("A", ActorDecl(Loc()))
        ads2 = ActorDecls()
        ads2.addActor("A", ActorDecl(Loc()))
        with self.assertRaisesRegex(ActorError, "Multiple declarations of actor A."):
            ads.addActors(ads2)

    def assertUnify(self, types1, j):
        [types2, _] = ActorDecls.unify1("A", "M", types1, False)
        self.assertEqual([str(t) for t in types2], j)

    def test_unify(self):
        # Basic single types.
        t = [[AnyType()], [], [], []]
        self.assertUnify(t, ["any"])

        t = [[], [AnyType()], [], []]
        self.assertUnify(t, ["any", "None"])

        t = [[], [], [AnyType()], []]
        self.assertUnify(t, ["None", "any"])

        t = [[], [AnyType()], [AnyType()], []]
        self.assertUnify(t, ["any", "any"])

        t = [[], [AnyType()], [AnyType()], [AnyType()]]
        self.assertUnify(t, ["any", "any"])

        t = [[], [], [AnyType()], [AnyType()]]
        self.assertUnify(t, ["None", "any"])

        # message and various query types
        m = "Message M of actor A has both message and query types."
        t = [[AnyType()], [AnyType()], [], []]
        with self.assertRaisesRegex(Exception, re.escape(m)):
            ActorDecls.unify1("A", "M", t, False)
        t = [[AnyType()], [], [AnyType()], []]
        with self.assertRaisesRegex(Exception, re.escape(m)):
            ActorDecls.unify1("A", "M", t, False)
        t = [[AnyType()], [], [], [AnyType()]]
        with self.assertRaisesRegex(Exception, re.escape(m)):
            ActorDecls.unify1("A", "M", t, False)

        # query reject only
        t = [[], [], [], [AnyType()]]
        m = (
            "Message M of actor A has a query reject type but not a query "
            + "resolve type, which we can't really represent."
        )
        with self.assertRaisesRegex(Exception, re.escape(m)):
            ActorDecls.unify1("A", "M", t, False)


if __name__ == "__main__":
    unittest.main()
