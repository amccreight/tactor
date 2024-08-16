#!/usr/bin/python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# Python representation of a subset of TypeScript.

import re


class JSType:
    def __str__(self):
        return "JSTYPE"

    def simplify(self):
        return


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


class TestOnlyType(JSType):
    def __init__(self):
        return

    def __eq__(self, o):
        return self.__class__ == o.__class__

    def __str__(self):
        return "testOnly"

    def jsonStr(self):
        return '"testOnly"'

    def __lt__(self, o):
        return self.classOrd() < o.classOrd()

    def classOrd(self):
        return 2


primitiveTypes = [
    "undefined",
    "string",
    "null",
    "boolean",
    "number",
    "structuredClone",
    "nsIPrincipal",
    "BrowsingContext",
    "DOMRect",
]
primRegexp = re.compile("|".join(primitiveTypes))


class PrimitiveType(JSType):
    def __init__(self, name):
        assert primRegexp.fullmatch(name)
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
        return 3


# This should be the same as the regexp from t_ID in ts_parse.py.
identifierRe = re.compile("(?!\\d)[\\w$]+")

# This is identifierRe with "-" and ":" additionally allowed after the first
# character, to reflect existing practice.
messageNameRe = re.compile("(?!(?:\\d|[-:]))[\\w$-:]+")


class JSPropertyType:
    def __init__(self, n, t, opt):
        assert isinstance(n, (int, str))
        assert isinstance(t, JSType)
        assert isinstance(opt, bool)
        self.name = n
        self.type = t
        self.optional = opt

    def __eq__(self, o):
        return (
            self.name == o.name and self.type == o.type and self.optional == o.optional
        )

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
        # XXX Need to implement int properties for the order to match.

        # Property names must be in order, without duplicates.
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
            l.append(f"[{p.jsonNameStr()}, {p.type.jsonStr()}{opt}]")
        return f'["object", {", ".join(l)}]'

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        # XXX Do I still need to use strings?
        return str(self) < str(o)

    def classOrd(self):
        return 4

    def simplify(self):
        for p in self.types:
            p.type.simplify()


class ArrayOrSetType(JSType):
    def __init__(self, isArray, elementType):
        assert elementType is not None
        self.isArray = isArray
        self.elementType = elementType

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.isArray == o.isArray and self.elementType == o.elementType

    def __str__(self):
        elementString = str(self.elementType)
        if self.isArray:
            return f"Array<{elementString}>"
        else:
            return f"Set<{elementString}>"

    def jsonStr(self):
        elementString = self.elementType.jsonStr()
        if self.isArray:
            return f'["array", {elementString}]'
        else:
            return f'["set", {elementString}]'

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        if self.isArray != o.isArray:
            return self.isArray < o.isArray
        return self.elementType < o.elementType

    def classOrd(self):
        return 5

    def simplify(self):
        self.elementType.simplify()


class MapType(JSType):
    def __init__(self, keyType, valueType):
        assert keyType is not None
        assert valueType is not None
        self.keyType = keyType
        self.valueType = valueType

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.keyType == o.keyType and self.valueType == o.valueType

    def __str__(self):
        keyString = str(self.keyType)
        valueString = str(self.valueType)
        return f"Map<{keyString}, {valueString}>"

    def jsonStr(self):
        keyString = self.keyType.jsonStr()
        valueString = self.valueType.jsonStr()
        return f'["map", {keyString}, {valueString}]'

    def __lt__(self, o):
        if self.classOrd() != o.classOrd():
            return self.classOrd() < o.classOrd()
        if self.keyType < o.keyType:
            return True
        if o.keyType < self.keyType:
            return False
        return self.valueType < o.valueType

    def classOrd(self):
        return 6

    def simplify(self):
        self.keyType.simplify()
        self.valueType.simplify()


class UnionType(JSType):
    def __init__(self, tt):
        assert len(tt) > 1
        self.types = tt

    def __eq__(self, o):
        if self.__class__ != o.__class__:
            return False
        return self.types == o.types

    def __str__(self):
        return " | ".join(sorted(map(lambda t: str(t), self.types)))

    def jsonStr(self):
        # ["union", t1, t2]
        assert len(self.types) >= 2
        s = self.types[0].jsonStr()
        for t in self.types[1:]:
            s = f'["union", {s}, {t.jsonStr()}]'
        return s

    def classOrd(self):
        return 7

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
                    # Clear t2 so it won't be used again. We've absorbed it
                    # entirely.
                    o.types[j] = None
                    # The original t1 might absorb multiple types in our
                    # union, so we need to keep trying with the new type.
                    t1 = t1New
            # t1 might have changed, so save it into the type.
            self.types[i] = t1

        # Copy over any remaining types from the union we're absorbing.
        for t2 in o.types:
            if t2 is None:
                continue
            self.types.append(t2)

    def absorbNonUnion(self, t2):
        assert not isinstance(t2, UnionType)
        newTypes = []
        for i in range(len(self.types)):
            t = self.types[i]
            assert not isinstance(t, UnionType)
            t2New = tryUnionWith(t, t2)
            if t2New is None:
                newTypes.append(t)
            else:
                # The original t2 might absorb multiple types in our union, so
                # we need to keep trying with the new type.
                t2 = t2New
        newTypes.append(t2)
        self.types = newTypes

    # The C++ logging does not use heuristics to combine object types, so this
    # union might contain multiple object types that we want to combine. This
    # process is quadratic, so we only want to do it on incoming logged types.
    def simplify(self):
        for t in self.types:
            t.simplify()

        newTypes = []
        for i in range(len(self.types)):
            ti = self.types[i]
            if ti is None:
                continue
            self.types[i] = None
            assert not isinstance(ti, UnionType)
            for j in range(i + 1, len(self.types)):
                tj = self.types[j]
                if tj is None:
                    continue
                assert not isinstance(tj, UnionType)
                tiNew = tryUnionWith(ti, tj)
                if tiNew is None:
                    continue
                self.types[j] = None
                ti = tiNew
            newTypes.append(ti)
        self.types = newTypes


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
    if isinstance(t1, TestOnlyType):
        if isinstance(t2, TestOnlyType):
            return t1
        else:
            return None
    if isinstance(t1, PrimitiveType):
        if t1 == t2:
            return t1
        return None
    if isinstance(t1, ObjectType):
        if not isinstance(t2, ObjectType):
            return None
        if objectAbsorb(t1, t2):
            return t1
        return None
    if isinstance(t1, ArrayOrSetType):
        if not isinstance(t2, ArrayOrSetType):
            return None
        if t1.isArray != t2.isArray:
            return None
        # Array<a|b> is nicer than Array<a> | Array<b> so always merge them,
        # unless one is being used as the type for an empty array.
        t1.elementType = unionWith(t1.elementType, t2.elementType)
        return t1
    if isinstance(t1, MapType):
        if not isinstance(t2, MapType):
            return None
        t1.keyType = unionWith(t1.keyType, t2.keyType)
        t1.valueType = unionWith(t1.valueType, t2.valueType)
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


def mergeObjects(t1, t2):
    stringNames1 = set([])
    for p in t1.types:
        stringNames1.add(p.name)
    stringNames2 = set([])
    for p in t2.types:
        stringNames2.add(p.name)

    # Merge if one set of properties is a subset of the other.
    if stringNames1 <= stringNames2 or stringNames2 <= stringNames1:
        return True

    bothNames = stringNames1 & stringNames2
    biggerSet = max(len(stringNames1), len(stringNames2))

    assert biggerSet > 0

    # XXX In my test example, there was a 3/5 match and a 3/4 match.
    if 2 * len(bothNames) <= biggerSet:
        return False
    return True


def objectAbsorb(t1, t2):
    assert isinstance(t1, ObjectType)
    assert isinstance(t2, ObjectType)

    # We assume all properties in both object types are sorted.

    if not mergeObjects(t1, t2):
        return False

    # XXX Need to implement integer properties, when I do that.
    stringProperties = []
    otherIndex = 0

    for p in t1.types:
        # Move over any smaller properties from the other object type.
        while otherIndex < len(t2.types) and t2.types[otherIndex] < p:
            stringProperties.append(t2.types[otherIndex])
            stringProperties[-1].optional = True
            otherIndex += 1

        if otherIndex < len(t2.types) and p.name == t2.types[otherIndex].name:
            # The leading properties have the same name, so merge them.
            p.type = unionWith(p.type, t2.types[otherIndex].type)
            stringProperties.append(p)
            stringProperties[-1].optional = (
                stringProperties[-1].optional or t2.types[otherIndex].optional
            )
            otherIndex += 1
        else:
            # p is smaller, so move it over.
            stringProperties.append(p)
            stringProperties[-1].optional = True

    # Move over any remaining properties from the other object type.
    while otherIndex < len(t2.types):
        stringProperties.append(t2.types[otherIndex])
        stringProperties[-1].optional = True
        otherIndex += 1

    t1.types = stringProperties
    return True
