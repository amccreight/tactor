#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import re

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
        return f'["primitive", "{self.name}"]'

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        return self.name < o.name

    def classOrd(self):
        return 1


# This should be the same as the regexp from t_ID in type_parse.py.
identifierRe = re.compile("(?!\d)[\w$]+")

class JSPropertyType:
    def __init__(self, n, t, opt):
        # XXX Need to implement support for integer names.
        assert isinstance(n, str)
        assert isinstance(t, JSType)
        assert isinstance(opt, bool)
        self.name = n
        self.type = t
        self.optional = opt

    def __eq__(self, o):
        return (self.name == o.name and self.type == o.type and
                self.optional == o.optional)

    def __lt__(self, o):
        return self.name < o.name

    def nameStr(self):
        m = identifierRe.fullmatch(self.name)
        if m:
            return self.name
        return self.jsonNameStr()

    def jsonNameStr(self):
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
                assert p.name > lastName
            lastName = p.name

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
        return 2


class ArrayType(JSType):
    def __init__(self, elementType):
        # elementType can be None to represent the type of an empty array.
        self.elementType = elementType

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.elementType == o.elementType

    def __str__(self):
        if self.elementType:
            elementString = str(self.elementType)
        else:
            elementString = "never"
        return f"Array<{elementString}>"

    def jsonStr(self):
        if self.elementType:
            return f'["array", {self.elementType.jsonStr()}]'
        else:
            return f'["array"]'

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        if self.elementType is None:
            return o.elementType is not None
        if o.elementType is None:
            return False
        return self.elementType < o.elementType

    def classOrd(self):
        return 3


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
        return 4

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
    if isinstance(t2, UnionType):
      t2.absorb(t1)
      return t2

    # Now deal with the remaining cases for t1.
    if isinstance(t1, AnyType):
        return t1
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
        if t1.elementType is None:
            return t2
        if t2.elementType is None:
            return t1
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
            types = list(messages[m])
            if len(types) == 1:
                newMessages[m] = types[0]
                # No need to log if we're not doing anything.
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
            newMessages[m] = tCombined
            if log:
                print(f"  COMBINED: {tCombined}")
        if log and loggedCurrentActor:
            print()

    return newActors


# Print out the types of actor messages, using the default TypeScript-like syntax.
def printMessageTypes(actors):
    for a in sorted(list(actors.keys())):
        mm = actors[a]
        print(a)
        for m in sorted(list(mm.keys())):
            print(f"  {m} {mm[m]}")
        print()


# Print out the types of actor messages, using the JSON syntax.
def printJSONMessageTypes(actors):
    print("{")
    for a in sorted(list(actors.keys())):
        mm = actors[a]
        print(f'  "{a}": {{')
        for m in sorted(list(mm.keys())):
            assert "\"" not in m
            print(f'    "{m}": {mm[m].jsonStr()},')
        print("  }")
    print("}")



if __name__ == "__main__":
    # XXX Change these to actually check the types.
    t1 = ObjectType([JSPropertyType("x", PrimitiveType("undefined"), False),
                     JSPropertyType("y", PrimitiveType("number"), False)])
    t2 = ObjectType([JSPropertyType("x", PrimitiveType("boolean"), False)])
    print(tryUnionWith(t1, t2))

    t1 = ObjectType([JSPropertyType("x", PrimitiveType("undefined"), False)])
    t2 = ObjectType([JSPropertyType("a", PrimitiveType("number"), False),
                     JSPropertyType("x", AnyType(), False)])
    print(tryUnionWith(t1, t2))

    t1 = ObjectType([JSPropertyType("x", UnionType([PrimitiveType("null"),
                                                    PrimitiveType("string")]), False)])
    t2 = ObjectType([JSPropertyType("x", UnionType([PrimitiveType("null"),
                                                    PrimitiveType("string")]), False)])
    print(tryUnionWith(t1, t2))

    assert str(ArrayType(None)) == "Array<never>"
