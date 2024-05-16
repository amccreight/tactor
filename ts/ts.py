#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Python representation of a subset of TypeScript.

import re
import sys
import unittest
import json


class JSType:
    def __str__(self):
        return "JSTYPE"


class AnyType(JSType):
    def __init__(self):
        return

    def __eq__(self, o):
        return self.__class__ == o.__class__

    def __str__(self):
        return "any"

    def jsonStr(self):
        return '"any"'

    def __lt__(self, o):
        return self.classOrd() < o.classOrd()

    def classOrd(self):
        return 0


class NeverType(JSType):
    def __init__(self):
        return

    def __eq__(self, o):
        return self.__class__ == o.__class__

    def __str__(self):
        return "never"

    def jsonStr(self):
        return '"never"'

    def __lt__(self, o):
        return self.classOrd() < o.classOrd()

    def classOrd(self):
        return 1


primitiveTypes = [
    "undefined",
    "string",
    "null",
    "boolean",
    "number",
    "nsIPrincipal",
    "BrowsingContext",
]
primRegexp = re.compile("|".join(primitiveTypes))

class PrimitiveType(JSType):
    def __init__(self, name):
        assert primRegexp.match(name)
        self.name = name

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.name == o.name

    def __str__(self):
        return self.name

    def jsonStr(self):
        return f'"{self.name}"'

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        return self.name < o.name

    def classOrd(self):
        return 2


# This should be the same as the regexp from t_ID in ts_parse.py.
identifierRe = re.compile("(?!\d)[\w$]+")

class JSPropertyType:
    def __init__(self, n, t, opt):
        # XXX Need to implement support for integer names.
        assert isinstance(n, str) or isinstance(n, int)
        assert isinstance(t, JSType)
        assert isinstance(opt, bool)
        self.name = n
        self.type = t
        self.optional = opt

    def __eq__(self, o):
        return (self.name == o.name and self.type == o.type and
                self.optional == o.optional)

    def __lt__(self, o):
        if isinstance(self.name, str):
            if isinstance(o.name, str):
                return self.name < o.name
            else:
                return True
        assert isinstance(self.name, int)
        if isinstance(o.name, str):
            return False
        return self.name < o.name

    def nameStr(self):
        if isinstance(self.name, int):
            return str(self.name)
        m = identifierRe.fullmatch(self.name)
        if m:
            return self.name
        return self.jsonNameStr()

    def jsonNameStr(self):
        if isinstance(self.name, int):
            return str(self.name)
        unescaped = self.name.replace('"', '\\"')
        return f'"{unescaped}"'


class ObjectType(JSType):
    def __init__(self, tt):
        # types is an array of JSPropertyTypes
        self.types = tt
        # XXX Need to implement int fields for the order to match.

        # Field names must be in order, without duplicates.
        lastName = None
        for p in tt:
            if lastName:
                assert p > lastName
            lastName = p

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.types == o.types

    def __str__(self):
        l = []
        for p in self.types:
            opt = "?" if p.optional else ""
            l.append(f"{str(p.nameStr())}{opt}: {p.type}")
        return f'{{{"; ".join(l)}}}'

    def jsonStr(self):
        if len(self.types) == 0:
            return '["object"]'
        l = []
        for p in self.types:
            opt = ", true" if p.optional else ""
            l.append(f'[{p.jsonNameStr()}, {p.type.jsonStr()}{opt}]')
        return f'["object", {", ".join(l)}]'

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        # XXX Do I still need to use strings?
        return str(self) < str(o)

    def classOrd(self):
        return 3


class ArrayType(JSType):
    def __init__(self, elementType):
        assert elementType is not None
        self.elementType = elementType

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.elementType == o.elementType

    def __str__(self):
        elementString = str(self.elementType)
        return f"Array<{elementString}>"

    def jsonStr(self):
        return f'["array", {self.elementType.jsonStr()}]'

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        return self.elementType < o.elementType

    def classOrd(self):
        return 4


class UnionType(JSType):
    def __init__(self, tt):
        assert len(tt) > 1
        self.types = tt

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.types == o.types

    def __str__(self):
        return " | ".join(map(lambda t: str(t), self.types))

    def jsonStr(self):
        # ["union", t1, t2]
        assert len(self.types) >= 2
        s = self.types[0].jsonStr()
        for t in self.types[1:]:
            s = f'["union", {s}, {t.jsonStr()}]'
        return s

    def classOrd(self):
        return 5

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        return self.types < o.types

    def absorb(self, o):
        if isinstance(o, UnionType):
            self.absorbUnion(o)
        else:
            self.absorbNonUnion(o)

    def absorbUnion(self, o):
        for i in range(len(self.types)):
            t1 = self.types[i]
            assert not isinstance(t1, UnionType)
            for j in range(len(o.types)):
                t2 = o.types[j]
                if t2 is None:
                    continue
                assert not isinstance(t2, UnionType)
                t1New = tryUnionWith(t1, t2)
                if t1New is not None:
                    # Clear t2 so it won't be used again. If a type unions with
                    # one member of a union, it shouldn't union with another.
                    o.types[j] = None
                    self.types[i] = t1New
                    break
        # Copy over any remaining types from the union we're absorbing.
        for t2 in o.types:
            if t2 is None:
                continue
            self.types.append(t2)

    def absorbNonUnion(self, t2):
        assert not isinstance(t2, UnionType)
        for t in self.types:
            assert not isinstance(t, UnionType)
            t2New = tryUnionWith(t, t2)
            if t2New is not None:
                t = t2New
                return
        self.types.append(t2)


# Reimplementation of JSActorMessageType::TryUnionWith()
def tryUnionWith(t1, t2):
    # Check a few "wildcard" cases on t2.
    if isinstance(t2, AnyType):
      return t2
    if isinstance(t2, NeverType):
      return t1
    if isinstance(t2, UnionType):
      t2.absorb(t1)
      return t2

    # Now deal with the remaining cases for t1.
    if isinstance(t1, AnyType):
        return t1
    if isinstance(t1, NeverType):
        return t2
    if isinstance(t1, PrimitiveType):
        if t1 == t2:
            return t1
        return None
    if isinstance(t1, ObjectType):
        if not isinstance(t2, ObjectType):
            return None
        objectAbsorb(t1, t2)
        return t1
    if isinstance(t1, ArrayType):
        if not isinstance(t2, ArrayType):
            return None
        # Array(a | b) is nicer than Array(a) | Array(b) so always merge them,
        # unless one is being used as the type for an empty array.
        t1.elementType = unionWith(t1.elementType, t2.elementType)
        return t1
    if isinstance(t1, UnionType):
        assert not isinstance(t2, UnionType)
        t1.absorbNonUnion(t2)
        return t1
    assert False

# Reimplementation of JSActorMessageType::UnionWith()
def unionWith(t1, t2):
    t3 = tryUnionWith(t1, t2)
    if not t3 is None:
        return t3
    return UnionType([t1, t2])

def objectAbsorb(t1, t2):
    assert isinstance(t1, ObjectType)
    assert isinstance(t2, ObjectType)

    # We assume all fields in both object types are sorted.

    # XXX Need to implement integer fields, when I do that.
    stringFieldTypes = []
    otherIndex = 0

    for p in t1.types:
        # Move over any smaller fields from the other object type.
        while otherIndex < len(t2.types) and t2.types[otherIndex] < p:
            stringFieldTypes.append(t2.types[otherIndex])
            stringFieldTypes[-1].optional = True
            otherIndex += 1

        if otherIndex < len(t2.types) and p.name == t2.types[otherIndex].name:
            # The leading fields have the same name, so merge them.
            p.type = unionWith(p.type, t2.types[otherIndex].type)
            stringFieldTypes.append(p)
            stringFieldTypes[-1].optional = stringFieldTypes[-1].optional or t2.types[otherIndex].optional
            otherIndex += 1
        else:
            # p is smaller, so move it over.
            stringFieldTypes.append(p)
            stringFieldTypes[-1].optional = True

    # Move over any remaining fields from the other object type.
    while otherIndex < len(t2.types):
        stringFieldTypes.append(t2.types[otherIndex])
        stringFieldTypes[-1].optional = True
        otherIndex += 1

    t1.types = stringFieldTypes

def enumToKind(kind):
    if kind == 0:
        return "Message"
    if kind == 1:
        return "Query"
    if kind == 2:
        return "QueryResolve"
    assert kind == 3
    return "QueryReject"

def unifyMessageTypes(actors, log=False):
    newActors = {}

    if log:
        print("Logging information about type combining")
        print()

    for a in sorted(list(actors.keys())):
        assert a not in newActors
        newMessages = {}
        newActors[a] = newMessages
        loggedCurrentActor = False
        messages = actors[a]
        for m in sorted(list(messages.keys())):
            kindTypes = messages[m]
            newMessages[m] = []
            lastValid = -1
            for kind in range(len(kindTypes)):
                types = kindTypes[kind]
                if len(types) == 0:
                    if kind == 3 and newMessages[m][2] is not None:
                        # If no reject type was specified, but a resolve type
                        # was, allow any type for the reject.
                        lastValid = kind
                        newMessages[m].append(AnyType())
                    else:
                        newMessages[m].append(None)
                    continue
                if len(types) == 1:
                    lastValid = kind
                    newMessages[m].append(types[0])
                    continue
                if log:
                    if not loggedCurrentActor:
                        loggedCurrentActor = True
                        print(a)
                    print(f"  {m}")
                    for t in sorted([str(t) for t in types]):
                        print(f"    {t}")
                tCombined = None
                for t in types:
                    if tCombined is None:
                        tCombined = t
                        continue
                    tCombined = unionWith(tCombined, t)
                    assert tCombined is not None
                lastValid = kind
                newMessages[m].append(tCombined)
                if log:
                    print(f"  {enumToKind(kind)} COMBINED: {tCombined}")
            assert lastValid > -1
            # Remove any trailing None.
            newMessages[m] = newMessages[m][:lastValid + 1]
        if log and loggedCurrentActor:
            print()

    return newActors


# Print out the types of actor messages, using the default TypeScript-like syntax.
def printMessageTypes(actors):
    for a in sorted(list(actors.keys())):
        mm = actors[a]
        print(a)
        for m in sorted(list(mm.keys())):
            types = mm[m]
            assert len(types) > 0
            assert len(types) <= 4
            if types[0] is not None:
                # Message
                print(f"  {m} : {types[0]}")
            if len(types) == 1:
                continue
            if types[1] is not None:
                # Query
                print(f"  {m} : {types[1]} => never")
            if len(types) == 2:
                continue
            hasType3 = types[2] is not None
            hasType4 = len(types) == 4 and types[3] is not None
            if hasType3 or hasType4:
                # QueryResolve and QueryReject.
                resolveType = types[2] if hasType3 else "never"
                rejectType = types[3] if hasType4 else "never"
                print(f"  {m} : never => [{resolveType}, {rejectType}]")

        print()

def serializeJSON(actors, s):
    s.addLine("{")
    firstActor = True
    for a in sorted(list(actors.keys())):
        mm = actors[a]
        if firstActor:
            firstActor = False
        else:
            s.addLine(",")
        s.addLine(f'  "{a}": {{')
        firstMessage = True
        for m in sorted(list(mm.keys())):
            if firstMessage:
                firstMessage = False
            else:
                s.addLine(",")
            assert "\"" not in m
            tt = [t.jsonStr() if t is not None else '"never"' for t in mm[m]]
            # For the JSON output, never include the QueryReject type. Instead,
            # let the checker implicitly treat that as "any".
            if len(tt) == 4:
                tt = tt[:3]
            s.add(f'    "{m}": [{", ".join(tt)}]')
        s.addLine("")
        s.add("  }")
    s.addLine("")
    s.addLine("}")

class printSerializer:
    def add(self, s):
        sys.stdout.write(s)
    def addLine(self, s):
        print(s)

# Print out the types of actor messages, using the JSON syntax.
def printJSONMessageTypes(actors):
    serializeJSON(actors, printSerializer())

class stringSerializer:
    def __init__(self):
        self.string = ""
    def add(self, s):
        self.string += s
    def addLine(self, s):
        self.string += s + "\n"

def stringJSONMessageTypes(actors):
    s = stringSerializer()
    serializeJSON(actors, s)
    return s.string

class TestUnion(unittest.TestCase):
    def test_basic(self):
        t1 = ObjectType([JSPropertyType("x", PrimitiveType("undefined"), False),
                         JSPropertyType("y", PrimitiveType("number"), False)])
        t2 = ObjectType([JSPropertyType("x", PrimitiveType("boolean"), False)])
        self.assertEqual(str(tryUnionWith(t1, t2)), "{x: undefined | boolean; y?: number}")

        t1 = ObjectType([JSPropertyType("x", PrimitiveType("undefined"), False)])
        t2 = ObjectType([JSPropertyType("a", PrimitiveType("number"), False),
                         JSPropertyType("x", AnyType(), False)])
        self.assertEqual(str(tryUnionWith(t1, t2)), "{a?: number; x: any}")

        t1 = ObjectType([JSPropertyType("x", UnionType([PrimitiveType("null"),
                                                        PrimitiveType("string")]), False)])
        t2 = ObjectType([JSPropertyType("x", UnionType([PrimitiveType("null"),
                                                        PrimitiveType("string")]), False)])
        self.assertEqual(str(tryUnionWith(t1, t2)), "{x: null | string}")

        self.assertEqual(str(ArrayType(NeverType())), "Array<never>")

        self.assertEqual(str(tryUnionWith(NeverType(), PrimitiveType("number"))), "number")
        self.assertEqual(str(tryUnionWith(PrimitiveType("number"), NeverType())), "number")


class TestActorJSON(unittest.TestCase):
    def test_valid(self):
        # Test that the actor and message stuff produces valid JSON.
        a0 = {}
        self.assertEqual(json.loads(stringJSONMessageTypes(a0)), {})

        a10 = {"a": {}}
        self.assertEqual(json.loads(stringJSONMessageTypes(a10)), {'a': {}})

        a1 = {"a": {"m": [PrimitiveType("undefined"), None, None, None]}}
        self.assertEqual(json.loads(stringJSONMessageTypes(a1)),
                        {'a': {'m': ['undefined', 'never', 'never']}})

        a1 = {"a": {"m": [PrimitiveType("undefined")]}}
        self.assertEqual(json.loads(stringJSONMessageTypes(a1)),
                        {'a': {'m': ['undefined']}})

        a1 = {"a": {"m": [None, PrimitiveType("undefined"), None, None]}}
        self.assertEqual(json.loads(stringJSONMessageTypes(a1)),
                        {'a': {'m': ['never', 'undefined', 'never']}})

        a1 = {"a": {"m": [None, None, PrimitiveType("undefined"), None]}}
        self.assertEqual(json.loads(stringJSONMessageTypes(a1)),
                        {'a': {'m': ['never', 'never', 'undefined']}})

        a1 = {"a": {"m": [PrimitiveType("undefined"), None, None, None]}}
        self.assertEqual(json.loads(stringJSONMessageTypes(a1)),
                        {'a': {'m': ['undefined', 'never', 'never']}})

        a2 = {"a": {"m1": [AnyType()], "m2": [AnyType()]}}
        self.assertEqual(json.loads(stringJSONMessageTypes(a2)),
                        {'a': {'m1': ['any'], 'm2': ['any']}})

        a3 = {"a": {"m1": [AnyType()]}, "b": {"m2": [AnyType()]}}
        self.assertEqual(json.loads(stringJSONMessageTypes(a3)),
                        {'a': {'m1': ['any']}, 'b': {'m2': ['any']}})

if __name__ == "__main__":
    unittest.main()
